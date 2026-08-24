"""Runtime state for omni-theme-cachy: generations, pointers, state.json.

Layout (all under ``$XDG_STATE_HOME/omni-theme``; never inside Git)::

    omni-theme/
    ├── generations/<id>/     immutable, complete theme snapshots
    │   └── manifest.json       (a promoted staging directory)
    ├── current  -> generations/<id>    symlink to the active generation
    ├── previous -> generations/<id>    symlink to the rollback target
    ├── staging/              scratch area for the next render
    ├── backups/              reserved for adapter-level backups
    └── state.json            engine metadata (this module's model)

Atomic promotion
----------------

The active generation is *never* mutated in place. Promotion swaps the
``current`` symlink atomically::

    tmp = <state>/.current.new
    os.symlink("generations/<new-id>", tmp)
    os.replace(tmp, <state>/current)

``os.replace`` over an existing symlink is a single same-filesystem
rename, so every reader sees either the old or the new generation —
never a missing or half-populated ``current``. Symlink targets are kept
*relative* so the whole state tree stays relocatable. This is the
prescribed primitive; a copy-based promotion
(``shutil.copytree(new, current, dirs_exist_ok=True)``) would expose a
window with mixed old/new content and is deliberately not used.

Ordering rule: on promote, ``previous`` is repointed at the outgoing
generation *before* ``current`` moves. A crash between the two swaps
leaves both links on the old generation — consistent, just not yet
advanced.

Ownership tracking
------------------

``state.json`` records every external file the engine last wrote
(``managed_targets``: path → sha256). Conflict inspection compares live
bytes against *those* hashes — not against the freshly rendered ones —
so re-theming your own output is safe while a hand-edited file is
flagged. An existing file the engine has no record of is treated as
user property and reported as a conflict.
"""

from __future__ import annotations

import itertools
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from core import filesystem
from core.errors import StateError
from core.staging import MANIFEST_FILE, Conflict, Manifest, load_manifest

__all__ = [
    "STATE_FILE",
    "STATE_VERSION",
    "GENERATIONS_DIR",
    "CURRENT_LINK",
    "PREVIOUS_LINK",
    "GenerationId",
    "ManagedTarget",
    "RuntimeState",
    "utc_now_iso",
    "new_generation_id",
    "ensure_layout",
    "generations_dir",
    "generation_dir",
    "read_state",
    "write_state",
    "link_target",
    "switch_link",
    "promote_generation",
    "revert_to_state",
    "load_generation_manifest",
    "manifest_hash_map",
    "inspect_managed_conflicts",
]

STATE_FILE = "state.json"
STATE_VERSION = 1
GENERATIONS_DIR = "generations"
STAGING_DIRNAME = "staging"
BACKUPS_DIRNAME = "backups"
CURRENT_LINK = "current"
PREVIOUS_LINK = "previous"

#: Sibling temp names for the atomic symlink swap.
_LINK_TMP = {CURRENT_LINK: ".current.new", PREVIOUS_LINK: ".previous.new"}

GenerationId = str
_GEN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")

_counter = itertools.count()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_generation_id(prefix: str = "gen") -> GenerationId:
    """Unique, sortable generation id (timestamp + pid + counter)."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{prefix}-{stamp}-{os.getpid()}-{next(_counter)}"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ManagedTarget:
    """One external file the engine wrote, with the hash it left there."""

    #: Absolute, expanded destination path.
    target: str
    #: SHA-256 of the content the engine last wrote.
    hash: str
    #: Logical template name that produced it, when known.
    name: str | None = None
    #: Adapter declared for the artifact, when any.
    adapter: str | None = None


@dataclass(frozen=True)
class RuntimeState:
    """Contents of ``state.json`` (plus in-memory use mid-activation)."""

    schema_version: int = STATE_VERSION
    current_theme: str | None = None
    previous_theme: str | None = None
    activated_at: str | None = None
    current_generation: GenerationId | None = None
    previous_generation: GenerationId | None = None
    managed_targets: tuple[ManagedTarget, ...] = ()
    adapters: dict[str, dict] = field(default_factory=dict)

    @property
    def managed_map(self) -> dict[str, ManagedTarget]:
        return {m.target: m for m in self.managed_targets}

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "current_theme": self.current_theme,
            "previous_theme": self.previous_theme,
            "activated_at": self.activated_at,
            "current_generation": self.current_generation,
            "previous_generation": self.previous_generation,
            "managed_targets": [
                {
                    "target": m.target,
                    "hash": m.hash,
                    "name": m.name,
                    "adapter": m.adapter,
                }
                for m in self.managed_targets
            ],
            "adapters": {
                aid: dict(summary) for aid, summary in sorted(self.adapters.items())
            },
        }

    @classmethod
    def from_dict(cls, raw: dict, *, source: str = STATE_FILE) -> "RuntimeState":
        if not isinstance(raw, dict):
            raise StateError(f"{source}: top level must be an object")
        version = raw.get("schema_version")
        if version != STATE_VERSION:
            raise StateError(
                f"{source}: unsupported state schema_version {version!r} "
                f"(expected {STATE_VERSION})"
            )

        targets_raw = raw.get("managed_targets", [])
        if not isinstance(targets_raw, list):
            raise StateError(f"{source}: 'managed_targets' must be a list")
        targets: list[ManagedTarget] = []
        for index, entry in enumerate(targets_raw):
            if not isinstance(entry, dict):
                raise StateError(f"{source}: managed_targets[{index}] must be an object")
            if not isinstance(entry.get("target"), str) or not isinstance(
                entry.get("hash"), str
            ):
                raise StateError(
                    f"{source}: managed_targets[{index}] needs string 'target' and 'hash'"
                )
            targets.append(
                ManagedTarget(
                    target=entry["target"],
                    hash=entry["hash"],
                    name=entry.get("name"),
                    adapter=entry.get("adapter"),
                )
            )

        adapters_raw = raw.get("adapters", {})
        if not isinstance(adapters_raw, dict):
            raise StateError(f"{source}: 'adapters' must be an object")

        def _opt_str(key: str) -> str | None:
            value = raw.get(key)
            return value if isinstance(value, str) else None

        return cls(
            schema_version=STATE_VERSION,
            current_theme=_opt_str("current_theme"),
            previous_theme=_opt_str("previous_theme"),
            activated_at=_opt_str("activated_at"),
            current_generation=_opt_str("current_generation"),
            previous_generation=_opt_str("previous_generation"),
            managed_targets=tuple(targets),
            adapters={str(k): dict(v) for k, v in adapters_raw.items() if isinstance(v, dict)},
        )


def _checked_gen_id(gen_id: GenerationId, what: str = "generation id") -> str:
    if not isinstance(gen_id, str) or not _GEN_ID_RE.match(gen_id) or ".." in gen_id:
        raise StateError(f"invalid {what}: {gen_id!r}")
    return gen_id


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------


def ensure_layout(state_root: str | Path) -> Path:
    """Create the state tree skeleton (never touches current/previous)."""
    root = Path(state_root).expanduser()
    for sub in (GENERATIONS_DIR, STAGING_DIRNAME, BACKUPS_DIRNAME):
        filesystem.ensure_dir(root / sub)
    return root


def generations_dir(state_root: str | Path) -> Path:
    return Path(state_root).expanduser() / GENERATIONS_DIR


def generation_dir(state_root: str | Path, gen_id: GenerationId) -> Path:
    return generations_dir(state_root) / _checked_gen_id(gen_id)


# ---------------------------------------------------------------------------
# state.json I/O
# ---------------------------------------------------------------------------


def read_state(state_root: str | Path) -> RuntimeState:
    """Load ``state.json``; a missing file means a fresh, empty state."""
    path = Path(state_root).expanduser() / STATE_FILE
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return RuntimeState()
    except OSError as exc:
        raise StateError(f"cannot read {path}: {exc}") from exc
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise StateError(f"invalid JSON in {path}: {exc}") from exc
    return RuntimeState.from_dict(raw, source=str(path))


def write_state(state_root: str | Path, state: RuntimeState) -> Path:
    """Atomically persist *state* as ``state.json``."""
    root = ensure_layout(Path(state_root).expanduser())
    payload = json.dumps(state.to_dict(), indent=2, sort_keys=False) + "\n"
    return filesystem.atomic_write_text(root / STATE_FILE, payload)


# ---------------------------------------------------------------------------
# Atomic pointer management
# ---------------------------------------------------------------------------


def link_target(state_root: str | Path, link_name: str) -> GenerationId | None:
    """Generation id *link_name* points at, or None when absent/not a link.

    Returns the bare id (``gen-…``), not the raw link text
    (``generations/gen-…``); anything unexpected reads as None.
    """
    link = Path(state_root).expanduser() / link_name
    if not link.is_symlink():
        return None
    raw = Path(os.readlink(link)).as_posix()
    prefix = f"{GENERATIONS_DIR}/"
    if raw.startswith(prefix) and raw != prefix:
        return raw[len(prefix):]
    return raw


def switch_link(state_root: str | Path, link_name: str, gen_id: GenerationId) -> Path:
    """Atomically point ``<state>/<link_name>`` at ``generations/<gen_id>``.

    Creates a sibling temp symlink and :func:`os.replace`s it over the
    real name — see the module docstring for why this is the promotion
    primitive. A non-symlink occupying the link name is refused instead
    of silently replaced (it predates the generation model).
    """
    root = Path(state_root).expanduser()
    _checked_gen_id(gen_id, link_name)
    link = root / link_name
    if os.path.lexists(link) and not link.is_symlink():
        raise StateError(
            f"{link} exists and is not a symlink; refusing to replace it "
            "(remove it or migrate the pre-generation layout manually)"
        )
    relative = f"{GENERATIONS_DIR}/{gen_id}"
    target = root / relative
    if not target.is_dir():
        raise StateError(f"cannot point {link_name} at missing generation: {target}")

    tmp = root / _LINK_TMP[link_name]
    tmp.unlink(missing_ok=True)
    try:
        os.symlink(relative, tmp)
        os.replace(tmp, link)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise StateError(f"cannot switch {link} to {relative}: {exc}") from exc
    return link


def promote_generation(
    state_root: str | Path,
    new_gen_id: GenerationId,
) -> GenerationId | None:
    """Make *new_gen_id* current; returns the displaced previous id (or None).

    ``previous`` is repointed at the outgoing current first, then
    ``current`` moves — each step is one atomic rename.
    """
    root = Path(state_root).expanduser()
    _checked_gen_id(new_gen_id)
    outgoing = link_target(root, CURRENT_LINK)
    if outgoing is not None:
        switch_link(root, PREVIOUS_LINK, outgoing)
    switch_link(root, CURRENT_LINK, new_gen_id)
    return outgoing


def revert_to_state(state_root: str | Path, prior_state: RuntimeState) -> None:
    """Restore both pointers to where *prior_state* says they were.

    Used when an activation fails after promotion but before the new
    state was persisted. Handles the first-activation case (no prior
    generation ⇒ remove the links entirely).
    """
    root = Path(state_root).expanduser()
    current_link = root / CURRENT_LINK
    previous_link = root / PREVIOUS_LINK

    if prior_state.previous_generation is not None:
        switch_link(root, PREVIOUS_LINK, prior_state.previous_generation)
    else:
        previous_link.unlink(missing_ok=True)

    if prior_state.current_generation is not None:
        switch_link(root, CURRENT_LINK, prior_state.current_generation)
    else:
        current_link.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Generations
# ---------------------------------------------------------------------------


def load_generation_manifest(state_root: str | Path, gen_id: GenerationId) -> Manifest:
    """Manifest of a stored generation; raises ManifestError when absent."""
    return load_manifest(generation_dir(state_root, gen_id) / MANIFEST_FILE)


def manifest_hash_map(manifest: Manifest) -> dict[str, str]:
    """Logical template name → rendered-content hash for one manifest."""
    return {entry.name: entry.hash for entry in manifest.files}


# ---------------------------------------------------------------------------
# Ownership-aware conflict inspection
# ---------------------------------------------------------------------------


def inspect_managed_conflicts(state: RuntimeState, manifest: Manifest) -> list[Conflict]:
    """Live files that diverge from what the engine last wrote there.

    Compared against ``state.managed_targets`` (the hashes recorded at
    the last successful apply), so:

    * absent file            → safe (fresh install);
    * bytes == last-written  → safe (ours, untouched);
    * anything else          → conflict. This includes files that exist
      but were never engine-written (untracked user content;
      ``managed_hash`` is empty then) — they are never overwritten
      without an explicit force policy.
    """
    managed = state.managed_map
    conflicts: list[Conflict] = []
    for entry in manifest.files:
        target = Path(entry.target).expanduser()
        record = managed.get(str(target))
        expected = record.hash if record is not None else ""
        try:
            actual = filesystem.sha256_file(target)
        except FileNotFoundError:
            continue
        except OSError:
            conflicts.append(Conflict(target=target, managed_hash=expected, actual_hash=None))
            continue
        if actual != expected:
            conflicts.append(
                Conflict(target=target, managed_hash=expected, actual_hash=actual)
            )
    return conflicts
