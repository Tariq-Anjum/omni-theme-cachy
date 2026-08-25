"""VS Code adapter: colorCustomizations merge with byte-surgical JSONC edits.

Exposes :class:`VscodeAdapter` plus focused helpers:

* :mod:`adapters.vscode.mapping` — semantic role → documented VS Code
  token table (the only keys this adapter may write);
* :mod:`adapters.vscode.jsonc` — JSONC reading and surgical merging;
* :mod:`adapters.vscode.adapter` — contract phases + rollback journal.

Metadata lives in Omni's own journal, never inside settings.json.
"""

from __future__ import annotations

from adapters.vscode.adapter import (
    Journal,
    VscodeAdapter,
    VscodePlan,
    discover_settings_file,
    journal_path,
)
from adapters.vscode.mapping import COLOR_CUSTOMIZATIONS_KEY, MANAGED_KEYS

__all__ = [
    "VscodeAdapter",
    "VscodePlan",
    "Journal",
    "journal_path",
    "discover_settings_file",
    "COLOR_CUSTOMIZATIONS_KEY",
    "MANAGED_KEYS",
]
