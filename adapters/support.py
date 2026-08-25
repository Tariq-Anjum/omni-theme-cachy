"""Shared file-snapshot plumbing for adapters that write owned artifacts.

Adapters that generate an owned file over a path that might pre-exist
(GTK direct ``gtk.css``, Konsole ``OmniTheme.colorscheme``) follow one
identical ownership protocol:

* before the first write, snapshot the original bytes into an
  Omni-private backup dir under ``<state>/adapters/<name>-backups/``;
* journal ``{"existed_before", "previous_hash", "backup_path"}``;
* rollback restores those bytes verbatim, or removes the file again
  when Omni created it.

Keeping this in one place means every adapter's rollback story is the
same story — audited once, tested once.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from core.errors import AdapterError
from core.filesystem import sha256_file

__all__ = ["snapshot_file", "restore_snapshot"]


def snapshot_file(target: str | Path, backup_dir: str | Path) -> dict:
    """Capture *target*'s current state for later :func:`restore_snapshot`.

    Returns the journal record. When the file does not exist the record
    simply says so (rollback will delete). Never modifies the target.
    """
    target_path = Path(target)
    record: dict = {
        "existed_before": target_path.is_file(),
        "previous_hash": None,
        "backup_path": None,
    }
    if not record["existed_before"]:
        return record

    digest = sha256_file(target_path)
    record["previous_hash"] = digest
    backups = Path(backup_dir)
    backups.mkdir(parents=True, exist_ok=True)
    backup = backups / f"{target_path.name}.{digest[:12]}.bak"
    if not backup.is_file():  # keep the first snapshot; never overwrite it
        shutil.copyfile(target_path, backup)
    record["backup_path"] = str(backup)
    return record


def restore_snapshot(target: str | Path, record: dict) -> tuple[bool, list[str]]:
    """Undo a journalled write: restore original bytes or remove the file.

    Returns ``(rolled_back, warnings)``. A missing record yields
    success-with-warning: there is nothing of ours to undo.
    """
    target_path = Path(target)
    warnings: list[str] = []
    try:
        if not record.get("existed_before"):
            target_path.unlink(missing_ok=True)
            return True, warnings
        backup = record.get("backup_path")
        if not backup or not Path(backup).is_file():
            return False, [
                f"rollback backup for {target_path} is missing ({backup!r}); "
                "file left as-is"
            ]
        shutil.copyfile(backup, target_path)
    except OSError as exc:
        return False, [f"cannot restore {target_path}: {exc}"]
    return True, warnings


def assert_within(directory: str | Path, candidate: str | Path) -> Path:
    """Path-traversal guard: *candidate* must resolve inside *directory*."""
    directory_path = Path(directory).expanduser().resolve()
    candidate_path = Path(candidate).expanduser()
    resolved = (
        candidate_path.resolve()
        if candidate_path.is_absolute()
        else (directory_path / candidate_path)
    ).resolve()
    if directory_path != resolved and directory_path not in resolved.parents:
        raise AdapterError(
            f"path escapes expected directory: {candidate_path} "
            f"is not under {directory_path}"
        )
    return resolved
