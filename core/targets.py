"""Explicit template→destination registry (``templates/targets.toml``).

The engine never guesses destination paths from template filenames: every
rendered artifact is declared here with explicit source/target metadata.
This keeps third-party themes from writing to surprising places and gives
the manifest something authoritative to record.

Registry schema (strictly validated)
-------------------------------------

.. code-block:: toml

    # templates/targets.toml — one [[template]] block per rendered file.
    [[template]]
    adapter = "kde-colorscheme"            # optional, informational

    [template.source]
    path = "kde/OmniTheme.colors.tpl"      # relative to the templates root;
                                           # must exist and end in '.tpl'

    [template.target]
    path = "~/.local/share/color-schemes/OmniTheme.colors"
                                           # absolute or '~/…'; never '..'

Validation is deliberately pedantic: unknown keys, missing fields,
relative destinations, ``..`` escapes, duplicate sources and duplicate
targets all raise :class:`core.errors.TargetsError` naming the offending
entry index.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from core.errors import TargetsError

__all__ = ["TARGETS_FILE", "TargetEntry", "load_targets"]

TARGETS_FILE = "targets.toml"

_ENTRY_KEYS = frozenset({"adapter", "source", "target"})
_SOURCE_KEYS = frozenset({"path"})
_TARGET_KEYS = frozenset({"path"})


@dataclass(frozen=True)
class TargetEntry:
    """One declared rendering: template *name* → destination *path*."""

    #: Template path relative to the templates root (posix style, ``.tpl``).
    name: str
    #: Absolute path of the template file under the templates root.
    source_path: Path
    #: Absolute, ``~``-expanded destination of the rendered file.
    target_path: Path
    #: Adapter that will consume the artifact, when declared.
    adapter: str | None


def _fail(registry: Path, message: str) -> TargetsError:
    return TargetsError(f"{registry}: {message}")


def _check_rel_path(value: object, what: str, registry: Path) -> PurePosixPath:
    if not isinstance(value, str) or not value.strip():
        raise _fail(registry, f"{what} must be a non-empty string")
    posix = PurePosixPath(value)
    if posix.is_absolute() or value.startswith("/") or "\\" in value:
        raise _fail(registry, f"{what} must be relative and posix-style, got {value!r}")
    if ".." in posix.parts:
        raise _fail(registry, f"{what} must not contain '..': {value!r}")
    return posix


def _check_dest_path(value: object, what: str, registry: Path) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise _fail(registry, f"{what} must be a non-empty string")
    expanded = Path(value).expanduser()
    if not expanded.is_absolute():
        raise _fail(
            registry,
            f"{what} must be absolute or '~/'-prefixed, got {value!r}",
        )
    if ".." in expanded.parts:
        raise _fail(registry, f"{what} must not contain '..': {value!r}")
    return expanded


def load_targets(
    registry_path: str | Path,
    *,
    templates_root: str | Path,
) -> list[TargetEntry]:
    """Parse and validate the registry at *registry_path*.

    *templates_root* is the directory source paths resolve against (the
    parent of the shipped ``templates/targets.toml``). Every source must
    exist on disk — a registry pointing at a vanished template is an
    error, not a silent skip. Returns entries in declaration order.
    """
    registry = Path(registry_path).expanduser()
    root = Path(templates_root).expanduser()

    try:
        with open(registry, "rb") as fh:
            data = tomllib.load(fh)
    except FileNotFoundError as exc:
        raise TargetsError(f"missing targets registry: {registry}") from exc
    except OSError as exc:
        raise TargetsError(f"cannot read {registry}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise TargetsError(f"invalid TOML in {registry}: {exc}") from exc

    raw_entries = data.get("template")
    if "template" not in data:
        raise _fail(registry, "missing 'template' key: declare [[template]] blocks")
    if not isinstance(raw_entries, list):
        raise _fail(registry, "'template' must be an array of [[template]] tables")

    known_top = set(data) - {"template"}
    if known_top:
        raise _fail(
            registry,
            f"unknown top-level key(s): {', '.join(sorted(known_top))} "
            "(only 'template' blocks are allowed)",
        )

    entries: list[TargetEntry] = []
    seen_names: set[str] = set()
    seen_targets: set[Path] = set()

    for index, raw in enumerate(raw_entries):
        label = f"[[template]] #{index}"
        if not isinstance(raw, dict):
            raise _fail(registry, f"{label} must be a table")
        unknown = set(raw) - _ENTRY_KEYS
        if unknown:
            raise _fail(registry, f"{label}: unknown key(s): {', '.join(sorted(unknown))}")

        adapter = raw.get("adapter")
        if adapter is not None and (not isinstance(adapter, str) or not adapter.strip()):
            raise _fail(registry, f"{label}: adapter must be a non-empty string")

        source = raw.get("source")
        if not isinstance(source, dict):
            raise _fail(registry, f"{label}: missing [template.source] table")
        unknown = set(source) - _SOURCE_KEYS
        if unknown:
            raise _fail(
                registry, f"{label}: unknown source key(s): {', '.join(sorted(unknown))}"
            )
        name_posix = _check_rel_path(source.get("path"), f"{label}: source.path", registry)
        if not name_posix.name.endswith(".tpl"):
            raise _fail(
                registry,
                f"{label}: source.path must end in '.tpl', got {name_posix}",
            )
        name = str(name_posix)
        source_path = root / name_posix
        if not source_path.is_file():
            raise _fail(registry, f"{label}: source template not found: {source_path}")

        target = raw.get("target")
        if not isinstance(target, dict):
            raise _fail(registry, f"{label}: missing [template.target] table")
        unknown = set(target) - _TARGET_KEYS
        if unknown:
            raise _fail(
                registry, f"{label}: unknown target key(s): {', '.join(sorted(unknown))}"
            )
        dest = _check_dest_path(target.get("path"), f"{label}: target.path", registry)

        if name in seen_names:
            raise _fail(registry, f"{label}: duplicate source {name!r}")
        if dest in seen_targets:
            raise _fail(registry, f"{label}: duplicate target {str(dest)!r}")
        seen_names.add(name)
        seen_targets.add(dest)

        entries.append(
            TargetEntry(
                name=name,
                source_path=source_path,
                target_path=dest,
                adapter=adapter.strip() if isinstance(adapter, str) else None,
            )
        )

    return entries
