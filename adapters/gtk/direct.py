"""Direct GTK CSS generation — an explicit, opt-in fallback capability.

Default policy (session 06): **never** write GTK files when KDE's own
kde-gtk-config integration can propagate colors. Direct generation
exists for machines without that integration and must be enabled
explicitly per adapter instance (``GtkAdapter(allow_direct=True)``).

Ownership rules for the fallback
--------------------------------
* The managed artifact is ``~/.config/gtk-{3,4}.0/gtk.css`` — the one
  CSS file GTK loads automatically from the user config dir.
* Content is wrapped in marker comments naming the owner and the source
  generation, so provenance is visible in the file itself::

      /* BEGIN omni-theme managed block (generation=…, theme=…) */
      …
      /* END omni-theme managed block */

* If the file does not exist → Omni creates it (whole file owned).
* If it exists *with* our markers → only the block is replaced; user
  CSS outside the block is preserved byte-for-byte.
* If it exists *without* markers → conflict: refuse unless ``force``,
  exactly like the engine treats diverged managed targets.
* Rollback restores the exact previous bytes (journalled before the
  first write); a file Omni created is removed again.

No ``chmod 444`` games: ownership comes from markers + journal, not
from read-only bits a platform service would happily ignore.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from core.errors import AdapterError
from core.filesystem import atomic_write_text, sha256_file

from adapters import support as gtk_support

__all__ = [
    "BEGIN_MARKER_PREFIX",
    "END_MARKER",
    "DirectWritePlan",
    "render_managed_block",
    "split_managed_block",
    "plan_direct_write",
    "apply_direct_write",
    "rollback_direct_write",
    "GtkJournal",
    "gtk_journal_path",
]

BEGIN_MARKER_PREFIX = "/* BEGIN omni-theme managed block"
END_MARKER = "/* END omni-theme managed block */"

JOURNAL_FILE = "gtk.json"


def gtk_journal_path(state_root: str | Path) -> Path:
    return Path(state_root) / "adapters" / JOURNAL_FILE


@dataclass
class GtkJournal:
    """Per-file rollback records for direct writes."""

    path: Path
    #: file path string → record
    files: dict[str, dict] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> "GtkJournal":
        p = Path(path)
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls(path=p)
        files = raw.get("files") if isinstance(raw, dict) else None
        return cls(path=p, files=dict(files) if isinstance(files, dict) else {})

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            self.path, json.dumps({"files": self.files}, indent=2) + "\n"
        )


def render_managed_block(colors: dict[str, str], *, generation: str, theme_id: str) -> str:
    """The complete owned CSS block for one generation."""
    lines = [
        f"{BEGIN_MARKER_PREFIX} (generation={generation}, theme={theme_id}) */",
        f"/* owner = omni-theme-cachy; source_generation = {generation or 'unknown'} */",
    ]
    lines.extend(
        f"@define-color {name} {value};" for name, value in sorted(colors.items())
    )
    lines.append(END_MARKER)
    return "\n".join(lines)


def split_managed_block(css_text: str) -> tuple[str | None, int, int]:
    """Locate an existing managed block.

    Returns ``(generation_or_None, start, end_exclusive)``; ``(None, -1,
    -1)`` when no block is present.
    """
    begin = css_text.find(BEGIN_MARKER_PREFIX)
    if begin == -1:
        return None, -1, -1
    end = css_text.find(END_MARKER, begin)
    if end == -1:
        raise AdapterError("existing gtk.css has a BEGIN omni-theme marker but no END")
    line_start = css_text.rfind("\n", 0, begin)
    header = css_text[line_start + 1 : begin]
    if header.strip():
        raise AdapterError("omni-theme BEGIN marker is not at the start of its line")

    comment_end = css_text.find("*/", begin)
    segment = css_text[begin : comment_end if comment_end != -1 else len(css_text)]
    match = re.search(r"generation=([^,\s)]+)", segment)
    return (match.group(1) if match else None), line_start + 1, end + len(END_MARKER)


@dataclass(frozen=True)
class DirectWritePlan:
    """What a direct write will do to one file (computed before writing)."""

    target: Path
    #: "create" | "replace-block" | "conflict" | "unchanged"
    action: str
    new_text: str
    previous_hash: str | None
    existing_generation: str | None

    @property
    def writable(self) -> bool:
        return self.action in ("create", "replace-block")


def plan_direct_write(
    target: Path,
    colors: dict[str, str],
    *,
    generation: str,
    theme_id: str,
    force: bool = False,
) -> DirectWritePlan:
    """Decide how *target* can receive the managed block (read-only)."""
    block = render_managed_block(colors, generation=generation, theme_id=theme_id)

    if not target.is_file():
        return DirectWritePlan(
            target=target,
            action="create",
            new_text=f"{block}\n",
            previous_hash=None,
            existing_generation=None,
        )

    current = target.read_text(encoding="utf-8")
    existing_generation, start, end = split_managed_block(current)
    if existing_generation is None:
        if not force:
            raise AdapterError(
                f"{target} exists without an omni-theme managed block; "
                "refusing to mix generated CSS into unknown content "
                "(force replaces the whole file)"
            )
        return DirectWritePlan(
            target=target,
            action="create",
            new_text=f"{block}\n",
            previous_hash=sha256_file(target),
            existing_generation=None,
        )

    _, new_gen, _ = split_managed_block(f"\n{block}\n")
    if current[start : end + 1] == block and existing_generation == new_gen:
        return DirectWritePlan(
            target=target,
            action="unchanged",
            new_text=current,
            previous_hash=sha256_file(target),
            existing_generation=existing_generation,
        )
    new_text = f"{current[:start]}{block}{current[end + 1 :]}"
    return DirectWritePlan(
        target=target,
        action="replace-block",
        new_text=new_text,
        previous_hash=sha256_file(target),
        existing_generation=existing_generation,
    )


def apply_direct_write(plan: DirectWritePlan, journal: GtkJournal, backup_dir: Path) -> bool:
    """Execute a plan; backs up prior bytes for exact rollback.

    When the file existed before Omni touched it, its original bytes are
    snapshotted under *backup_dir* (Omni-owned state) and journalled;
    rollback copies them back verbatim. Returns True when bytes changed.
    """
    key = str(plan.target)
    if plan.action == "unchanged":
        return False

    if key not in journal.files:
        journal.files[key] = gtk_support.snapshot_file(plan.target, backup_dir)

    atomic_write_text(plan.target, plan.new_text)
    return True


def rollback_direct_write(target: Path, journal: GtkJournal) -> tuple[bool, list[str]]:
    """Restore *target* to its pre-Omni state per the journal.

    Returns (rolled_back, warnings). Missing journal entry → warning,
    success=True (nothing of ours to undo).
    """
    record = journal.files.get(str(target))
    if record is None:
        return True, [f"no direct-write record for {target}; leaving file untouched"]

    rolled, warnings = gtk_support.restore_snapshot(target, record)
    if rolled:
        del journal.files[str(target)]
    return rolled, warnings
