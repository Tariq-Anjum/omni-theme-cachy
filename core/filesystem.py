"""Filesystem primitives for omni-theme-cachy.

Everything here is deliberately boring and side-effect-explicit:

* **Runtime directories** follow XDG Base Directory semantics. ``$XDG_*``
  environment variables are honored *at call time* (never cached at
  import) so tests can point every helper at a temporary fake ``$HOME``
  without leaking state between tests.

* **Atomic writes** never leave a half-written file visible at the
  target path: content goes to a sibling temp file, is flushed and
  fsync'ed, chmod'ed, then moved into place with :func:`os.replace`
  (atomic within a filesystem). An existing file's permission bits are
  preserved across replacement so user tweaks like ``chmod 600`` survive
  re-theming.

* **Directory promotion** implements the two-step rename dance used by
  activation (session 04): the live directory moves aside into a
  timestamped backup slot first, then staging takes its place. Each step
  is a single rename on one filesystem; a crash between them leaves
  either the old or the new theme, never a mixture.

No hashing, rendering or policy lives here — see :mod:`core.staging`.
"""

from __future__ import annotations

import itertools
import os
import shutil
import tempfile
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from core.errors import PathPolicyError

__all__ = [
    "home_dir",
    "xdg_config_home",
    "xdg_data_home",
    "xdg_state_home",
    "omni_config_dir",
    "omni_data_dir",
    "omni_state_dir",
    "state_current_dir",
    "state_previous_dir",
    "state_staging_dir",
    "state_backups_dir",
    "approved_roots",
    "set_approved_roots",
    "validate_write_target",
    "sha256_bytes",
    "sha256_file",
    "ensure_dir",
    "clean_directory",
    "atomic_write",
    "atomic_write_text",
    "backup_slot_name",
    "promote_directory",
]

_ENV_CONFIG = "XDG_CONFIG_HOME"
_ENV_DATA = "XDG_DATA_HOME"
_ENV_STATE = "XDG_STATE_HOME"

DEFAULT_FILE_MODE = 0o644

_backup_counter = itertools.count()


def home_dir() -> Path:
    """The user's home directory (``$HOME``), resolved at call time."""
    return Path.home()


def _xdg(env_var: str, default_suffix: str) -> Path:
    """Resolve one XDG base directory, honoring its env override."""
    value = os.environ.get(env_var)
    if value and value.strip():
        return Path(value).expanduser()
    return home_dir() / default_suffix


def xdg_config_home() -> Path:
    """``$XDG_CONFIG_HOME`` or ``~/.config``."""
    return _xdg(_ENV_CONFIG, ".config")


def xdg_data_home() -> Path:
    """``$XDG_DATA_HOME`` or ``~/.local/share``."""
    return _xdg(_ENV_DATA, ".local/share")


def xdg_state_home() -> Path:
    """``$XDG_STATE_HOME`` or ``~/.local/state``."""
    return _xdg(_ENV_STATE, ".local/state")


def omni_config_dir() -> Path:
    """Engine config root: user overlays, templates and settings live here."""
    return xdg_config_home() / "omni-theme"


def omni_data_dir() -> Path:
    """Engine data root (generated artifacts that are not pure state)."""
    return xdg_data_home() / "omni-theme"


def omni_state_dir() -> Path:
    """Engine state root: current theme pointer, staging, backups."""
    return xdg_state_home() / "omni-theme"


def state_current_dir() -> Path:
    """The promoted, currently-active theme snapshot."""
    return omni_state_dir() / "current"


def state_previous_dir() -> Path:
    """The previous complete theme snapshot (rollback source)."""
    return omni_state_dir() / "previous"


def state_staging_dir() -> Path:
    """Where the next theme is rendered before promotion."""
    return omni_state_dir() / "staging"


def state_backups_dir() -> Path:
    """Timestamped slots holding directories displaced by promotion."""
    return omni_state_dir() / "backups"


# ---------------------------------------------------------------------------
# Central write policy: approved roots, containment, ownership
# ---------------------------------------------------------------------------
#
# Every managed filesystem write must pass through :func:`validate_write_target`
# (enforced inside :func:`atomic_write`, which is the engine's only write
# primitive). The approved write-target set is exactly the XDG-derived base
# directories defined above — nothing broader is ever approved.

_approved_roots_override: tuple[Path, ...] | None = None


def set_approved_roots(roots) -> None:
    """Override the approved write roots (test/sandbox hook; ``None`` restores
    the XDG-derived defaults). Values may be relative to the current env."""
    global _approved_roots_override
    _approved_roots_override = (
        None if roots is None else tuple(Path(r).expanduser() for r in roots)
    )


def approved_roots() -> tuple[Path, ...]:
    """The single named allowlist of writable roots, resolved at call time.

    Defaults to the XDG-derived base directories (``$XDG_CONFIG_HOME``,
    ``$XDG_DATA_HOME``, ``$XDG_STATE_HOME``). Every engine-owned write
    destination — state tree, staging, overlays, adapter targets —
    resolves inside one of these.
    """
    if _approved_roots_override is not None:
        return tuple(p.resolve(strict=False) for p in _approved_roots_override)
    return (
        xdg_config_home().resolve(strict=False),
        xdg_data_home().resolve(strict=False),
        xdg_state_home().resolve(strict=False),
    )


def _containing_root(resolved: Path) -> Path | None:
    for root in approved_roots():
        if resolved == root or root in resolved.parents:
            return root
    return None


def _check_parent_ownership(node: Path) -> None:
    st = node.stat()
    mode = st.st_mode
    if st.st_uid != os.geteuid():
        raise PathPolicyError(
            f"unsafe ownership: {node} is owned by uid {st.st_uid}, "
            "not the current user"
        )
    if mode & 0o020:
        raise PathPolicyError(f"unsafe permissions: {node} is group-writable")
    if mode & 0o002 and not mode & 0o1000:
        raise PathPolicyError(
            f"unsafe permissions: {node} is world-writable without the sticky bit"
        )


def _check_target_ownership(target: Path) -> None:
    st = target.stat()
    mode = st.st_mode
    if st.st_uid != os.geteuid():
        raise PathPolicyError(
            f"unsafe ownership: {target} is owned by uid {st.st_uid}, "
            "not the current user"
        )
    if mode & 0o020:
        raise PathPolicyError(f"unsafe permissions: {target} is group-writable")
    if mode & 0o002:
        raise PathPolicyError(f"unsafe permissions: {target} is world-writable")
    if mode & 0o6000:
        raise PathPolicyError(
            f"unsafe permissions: {target} has setuid/setgid bits"
        )


def validate_write_target(path: str | Path) -> Path:
    """Central gate for every managed filesystem write.

    Canonicalizes *path*, resolves symlinks, then enforces:

    * containment inside one :func:`approved_roots` entry (sibling-prefix
      and ``..`` escapes are rejected; a nonexistent final component is
      allowed, its existing ancestors must resolve inside the root);
    * symlink escapes (resolution of any component leaving the root);
    * the ownership policy: current-user ownership, no group/world
      write bits, no setuid/setgid on the target, and no world-writable
      (non-sticky) or group-writable parents up to the approved root.

    Violations raise :class:`core.errors.PathPolicyError`; the engine
    never repairs ownership or permissions. Returns the resolved path.
    """
    raw = Path(path).expanduser()
    resolved = raw.resolve(strict=False)
    root = _containing_root(resolved)
    if root is None:
        raise PathPolicyError(
            f"write target {raw} resolves to {resolved}, which is outside "
            "the approved write roots"
        )
    if resolved.exists():
        _check_target_ownership(resolved)
    node = root if resolved == root else resolved.parent
    while node != root:
        if node.exists():
            _check_parent_ownership(node)
        node = node.parent
    if root.exists():
        _check_parent_ownership(root)
    return resolved


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


def sha256_bytes(data: bytes) -> str:
    """Lowercase hex SHA-256 of *data*."""
    return sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    """Lowercase hex SHA-256 of the file at *path* (streamed)."""
    digest = sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Directories
# ---------------------------------------------------------------------------


def ensure_dir(path: str | Path) -> Path:
    """Create *path* (and parents) if needed; returns the resolved path."""
    resolved = Path(path).expanduser()
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def clean_directory(path: str | Path) -> Path:
    """Remove every entry inside *path*, keeping the directory itself.

    Used to guarantee a pristine staging area: leftovers from an aborted
    run can never leak into a new render. Missing directory → created.
    """
    resolved = ensure_dir(path)
    for entry in resolved.iterdir():
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()
    return resolved


# ---------------------------------------------------------------------------
# Atomic writes
# ---------------------------------------------------------------------------


def atomic_write(
    path: str | Path,
    data: bytes,
    *,
    mode: int | None = None,
) -> Path:
    """Replace the file at *path* with *data* atomically.

    Steps: create parent directories safely; write a sibling temp file;
    flush; fsync; apply permissions (explicit *mode*, else preserve the
    existing file's mode, else ``0o644``); :func:`os.replace` over the
    destination. On failure the temp file is removed and the destination
    keeps its previous bytes. The target must pass
    :func:`validate_write_target` (containment + ownership policy) or a
    :class:`core.errors.PathPolicyError` is raised and nothing changes.
    """
    target = validate_write_target(path)
    parent = ensure_dir(target.parent)

    try:
        existing_mode = target.stat().st_mode & 0o7777
    except FileNotFoundError:
        existing_mode = None
    effective_mode = mode if mode is not None else (
        existing_mode if existing_mode is not None else DEFAULT_FILE_MODE
    )

    fd, tmp_name = tempfile.mkstemp(
        dir=parent, prefix=f".{target.name}.", suffix=".tmp"
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp_path, effective_mode)
        os.replace(tmp_path, target)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    return target


def atomic_write_text(path: str | Path, text: str, *, mode: int | None = None) -> Path:
    """:func:`atomic_write` for UTF-8 text."""
    return atomic_write(path, text.encode("utf-8"), mode=mode)


# ---------------------------------------------------------------------------
# Directory promotion (used by activation; exercised from session 03 tests)
# ---------------------------------------------------------------------------


def backup_slot_name(label: str) -> str:
    """Unique, sortable slot name for a displaced directory.

    Format ``<label>-<UTC timestamp>-<pid>-<counter>`` — collisions are
    impossible even under rapid repeated calls in tests.
    """
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{label}-{stamp}-{os.getpid()}-{next(_backup_counter)}"


def promote_directory(
    new: str | Path,
    current: str | Path,
    *,
    backup_root: str | Path | None = None,
) -> Path:
    """Atomically install the directory *new* at *current*.

    When *current* exists it first moves into a timestamped slot under
    *backup_root* (required when a replacement is expected); then *new*
    renames onto *current*. Both steps are same-filesystem renames.
    Returns the *current* path. Neither argument may be a symlink.
    """
    new_path = Path(new).expanduser()
    current_path = Path(current).expanduser()
    if not new_path.is_dir():
        raise NotADirectoryError(f"nothing to promote: {new_path}")
    if current_path.is_symlink() or new_path.is_symlink():
        raise OSError("refusing to promote through a symlink")

    if current_path.exists():
        if backup_root is None:
            raise FileExistsError(
                f"{current_path} exists and no backup_root was given"
            )
        slots = ensure_dir(backup_root)
        os.replace(current_path, slots / backup_slot_name(current_path.name))
    else:
        if backup_root is not None:
            ensure_dir(backup_root)
    ensure_dir(current_path.parent)
    os.replace(new_path, current_path)
    return current_path
