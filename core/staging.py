"""Atomic staging: render everything first, touch nothing live.

The full pipeline (session 03 scope)::

    resolve theme
      → load
      → deep-merge user overlay (~/.config/omni-theme/themes/<theme>)
      → validate values (loader does this strictly)
      → render every registered target (template precedence:
        user → theme → built-in)
      → write results into a CLEAN staging directory
      → record manifest.json describing planned writes

Nothing here reads or writes any live desktop configuration and nothing
outside ``<state>/staging/`` is modified. Promotion onto ``current/``
(and therefore the first moment a real file could change) belongs to
activation (session 04), which consumes :class:`StageResult` and
:func:`detect_conflicts`.

Ownership model
---------------
* ``base``          — rendered purely from the shipped theme.
* ``user-overlay``  — at least one palette/surface value came from the
                      user's overlay directory.

Per-file provenance is finer-grained: ``origin`` records which template
tier won resolution (``user`` / ``theme`` / ``builtin``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from core import filesystem
from core.errors import ManifestError, StagingError
from core.renderer import (
    build_context,
    render_template_file,
    resolve_template,
)
from core.targets import TargetEntry, load_targets
from core.theme_loader import load_theme_with_overlay

__all__ = [
    "MANIFEST_FILE",
    "MANIFEST_VERSION",
    "ManifestFileEntry",
    "Manifest",
    "StagedFile",
    "StageResult",
    "Conflict",
    "stage_theme",
    "manifest_to_dict",
    "write_manifest",
    "load_manifest",
    "detect_conflicts",
]

MANIFEST_FILE = "manifest.json"
MANIFEST_VERSION = 1


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StagedFile:
    """One rendered artifact sitting in staging, awaiting promotion."""

    #: Logical template name (registry key, e.g. ``kde/X.colors.tpl``).
    name: str
    #: Absolute path of the template file actually used.
    source: Path
    #: Which resolution tier supplied the template.
    origin: str
    #: Absolute destination after promotion.
    target: Path
    #: Adapter declared for the artifact, when any.
    adapter: str | None
    #: SHA-256 of the rendered bytes.
    hash: str
    #: Artifact path relative to the staging root (posix).
    staged: str


@dataclass(frozen=True)
class ManifestFileEntry:
    """JSON round-trip shape of :class:`StagedFile`."""

    name: str
    source: str
    origin: str
    target: str
    adapter: str | None
    hash: str
    staged: str


@dataclass(frozen=True)
class Manifest:
    """What we intend to write, fully described before writing it."""

    theme_name: str
    theme_id: str
    theme_version: int
    mode: str
    theme_source: Path
    timestamp: str
    ownership: str  # "base" | "user-overlay"
    files: tuple[ManifestFileEntry, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Conflict:
    """A live file diverged from the hash we last managed."""

    target: Path
    managed_hash: str
    #: Current SHA-256 (``None`` when the file exists but cannot be read).
    actual_hash: str | None


@dataclass(frozen=True)
class StageResult:
    staging_dir: Path
    manifest_path: Path
    files: tuple[StagedFile, ...]
    ownership: str


# ---------------------------------------------------------------------------
# Manifest serialization
# ---------------------------------------------------------------------------


def manifest_to_dict(manifest: Manifest) -> dict:
    return {
        "version": MANIFEST_VERSION,
        "theme": {
            "name": manifest.theme_name,
            "id": manifest.theme_id,
            "version": manifest.theme_version,
            "mode": manifest.mode,
        },
        "theme_source": str(manifest.theme_source),
        "timestamp": manifest.timestamp,
        "ownership": manifest.ownership,
        "files": [
            {
                "name": f.name,
                "source": str(f.source),
                "origin": f.origin,
                "target": str(f.target),
                "adapter": f.adapter,
                "hash": f.hash,
                "staged": f.staged,
            }
            for f in manifest.files
        ],
    }


def write_manifest(manifest: Manifest, path: str | Path) -> Path:
    """Atomically write *manifest* as JSON to *path*."""
    payload = json.dumps(manifest_to_dict(manifest), indent=2, sort_keys=False) + "\n"
    return filesystem.atomic_write_text(path, payload)


_REQUIRED_ENTRY_KEYS = frozenset(
    {"name", "source", "origin", "target", "hash", "staged"}
)


def load_manifest(path: str | Path) -> Manifest:
    """Read and structurally validate a ``manifest.json``."""
    manifest_path = Path(path).expanduser()
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ManifestError(f"missing manifest: {manifest_path}") from exc
    except OSError as exc:
        raise ManifestError(f"cannot read {manifest_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ManifestError(f"invalid JSON in {manifest_path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ManifestError(f"{manifest_path}: top level must be an object")
    version = raw.get("version")
    if version != MANIFEST_VERSION:
        raise ManifestError(
            f"{manifest_path}: unsupported manifest version {version!r} "
            f"(expected {MANIFEST_VERSION})"
        )

    theme = raw.get("theme")
    if not isinstance(theme, dict):
        raise ManifestError(f"{manifest_path}: missing 'theme' object")
    try:
        meta_tuple = (theme["name"], theme["id"], theme["mode"])
        theme_version = theme["version"]
    except KeyError as exc:
        raise ManifestError(f"{manifest_path}: theme missing {exc}") from None
    if isinstance(theme_version, bool) or not isinstance(theme_version, int):
        raise ManifestError(f"{manifest_path}: theme.version must be an integer")

    files_raw = raw.get("files")
    if not isinstance(files_raw, list):
        raise ManifestError(f"{manifest_path}: 'files' must be a list")

    files: list[ManifestFileEntry] = []
    for index, entry in enumerate(files_raw):
        if not isinstance(entry, dict):
            raise ManifestError(f"{manifest_path}: files[{index}] must be an object")
        missing = _REQUIRED_ENTRY_KEYS - set(entry)
        if missing:
            raise ManifestError(
                f"{manifest_path}: files[{index}] missing keys: "
                f"{', '.join(sorted(missing))}"
            )
        files.append(
            ManifestFileEntry(
                name=entry["name"],
                source=entry["source"],
                origin=entry.get("origin", "builtin"),
                target=entry["target"],
                adapter=entry.get("adapter"),
                hash=entry["hash"],
                staged=entry["staged"],
            )
        )

    ownership = raw.get("ownership", "base")

    return Manifest(
        theme_name=meta_tuple[0],
        theme_id=meta_tuple[1],
        theme_version=theme_version,
        mode=meta_tuple[2],
        theme_source=Path(raw.get("theme_source", ".")),
        timestamp=raw.get("timestamp", ""),
        ownership=ownership,
        files=tuple(files),
    )


# ---------------------------------------------------------------------------
# Conflicts
# ---------------------------------------------------------------------------


def detect_conflicts(manifest: Manifest) -> list[Conflict]:
    """Compare live target files against hashes recorded in *manifest*.

    A target is safe to update when its current bytes still hash to the
    value recorded when the engine last wrote it. Anything else — edited
    by hand, replaced by another tool — is reported as a
    :class:`Conflict`; callers must surface these instead of overwriting
    silently (a CLI ``--force`` arrives in a later session).
    """
    conflicts: list[Conflict] = []
    for entry in manifest.files:
        target = Path(entry.target).expanduser()
        try:
            actual = filesystem.sha256_file(target)
        except FileNotFoundError:
            continue  # fresh install: nothing to clobber
        except OSError:
            conflicts.append(Conflict(target=target, managed_hash=entry.hash, actual_hash=None))
            continue
        if actual != entry.hash:
            conflicts.append(
                Conflict(target=target, managed_hash=entry.hash, actual_hash=actual)
            )
    return conflicts


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stage_theme(
    theme_dir: str | Path,
    *,
    registry_path: str | Path,
    templates_root: str | Path,
    user_theme_overlay_dir: str | Path | None = None,
    user_templates_dir: str | Path | None = None,
    state_root: str | Path | None = None,
) -> StageResult:
    """Render every registered target for *theme_dir* into clean staging.

    Parameters map onto the runtime layout::

        registry_path             …/templates/targets.toml
        templates_root            …/templates           (built-in tier)
        user_theme_overlay_dir    ~/.config/omni-theme/themes/<theme>
        user_templates_dir        ~/.config/omni-theme/templates
        state_root                $XDG_STATE_HOME/omni-theme

    Raises :class:`core.errors.StagingError` (wrapping render failures)
    when the pipeline cannot produce a complete, consistent staging
    directory; the exception message names the failing template.
    """
    templates_root = Path(templates_root).expanduser()
    entries: list[TargetEntry] = load_targets(registry_path, templates_root=templates_root)

    theme, overlay = load_theme_with_overlay(theme_dir, user_theme_overlay_dir)
    context = build_context(theme)

    state = Path(state_root).expanduser() if state_root else filesystem.omni_state_dir()
    staging = filesystem.clean_directory(state / "staging")

    staged_files: list[StagedFile] = []
    user_templates = (
        Path(user_templates_dir).expanduser() if user_templates_dir else None
    )
    for entry in entries:
        resolved = resolve_template(
            entry.name,
            theme_dir=theme.path,
            user_templates_dir=user_templates,
            builtin_root=templates_root,
        )
        try:
            rendered = render_template_file(resolved.path, context)
        except Exception as exc:
            raise StagingError(
                f"rendering {entry.name!r} (from {resolved.path}) failed: {exc}"
            ) from exc
        if not rendered.strip():
            raise StagingError(
                f"template {entry.name!r} rendered to an empty file; "
                "refusing to stage it"
            )

        staged_rel = _staged_name(entry.name)
        staged_abs = staging / staged_rel
        data = rendered.encode("utf-8")
        filesystem.atomic_write(staged_abs, data)

        staged_files.append(
            StagedFile(
                name=entry.name,
                source=resolved.path,
                origin=resolved.origin,
                target=entry.target_path,
                adapter=entry.adapter,
                hash=filesystem.sha256_bytes(data),
                staged=staged_rel.as_posix(),
            )
        )

    manifest = Manifest(
        theme_name=theme.meta.name,
        theme_id=theme.meta.id,
        theme_version=theme.meta.version,
        mode=theme.mode,
        theme_source=theme.path if theme.path else Path(theme_dir),
        timestamp=_utc_now(),
        ownership=overlay.ownership,
        files=tuple(
            ManifestFileEntry(
                name=f.name,
                source=str(f.source),
                origin=f.origin,
                target=str(f.target),
                adapter=f.adapter,
                hash=f.hash,
                staged=f.staged,
            )
            for f in staged_files
        ),
    )
    manifest_path = write_manifest(manifest, staging / MANIFEST_FILE)

    return StageResult(
        staging_dir=staging,
        manifest_path=manifest_path,
        files=tuple(staged_files),
        ownership=overlay.ownership,
    )


def _staged_name(template_name: str) -> PurePosixPath:
    """Staged artifact name for a template name: ``x/y.tpl`` → ``x/y``."""
    posix = PurePosixPath(template_name)
    if posix.name.endswith(".tpl"):
        return posix.with_name(posix.name[: -len(".tpl")])
    return posix
