"""Central, section-safe operations on KDE/KConfig INI-style text.

KDE configuration files (``kdeglobals``, ``konsolerc``, Konsole
``*.profile``, ``*.colors``/``*.colorscheme``) use KConfig semantics
that generic INI parsers do not preserve:

* keys may carry bracket suffixes — ``key[$e]``, ``key[$i]``, locale
  tags such as ``key[en_US]`` — that alter KConfig behaviour and must
  never be corrupted or duplicated by an edit;
* the same group may legally appear more than once (later assignments
  win);
* comments, blank lines, indentation and key order are user-visible
  state.

``configparser`` lowercases keys, rejects duplicate sections and would
re-serialise the whole file, so it is deliberately not used. This module
treats the text as the source of truth and performs bounded edits: only
the managed key line (or one inserted line) ever changes.

Mechanism choice per file (session 13): where KDE-native tooling is the
documented mechanism it stays (``plasma-apply-colorscheme`` writes
kdeglobals; ``kreadconfig6`` reads it back — Omni never writes that file
itself). Files the engine legitimately touches are edited here and
persisted through ``core.filesystem.atomic_write_text`` — the validated
atomic write path — never through ad-hoc writes.
"""

from __future__ import annotations

__all__ = ["parse_ini", "set_ini_key", "remove_ini_key"]


def parse_ini(text: str) -> dict[tuple[str, str], str]:
    """Parse KConfig-style INI text into ``((group, key), value)``.

    Later assignments win (KConfig last-wins semantics). Keys are kept
    verbatim: a ``ColorScheme[$e]`` suffix remains part of the key, so
    suffixed and plain variants stay distinct entries. Lines before any
    group header are recorded under the empty group name.
    """
    result: dict[tuple[str, str], str] = {}
    group = ""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            group = stripped[1:-1]
            continue
        if "=" in stripped:
            key, _, value = stripped.partition("=")
            result[(group, key.strip())] = value.strip()
    return result


def set_ini_key(
    text: str, section: str, key: str, value: str
) -> tuple[str, str | None, bool]:
    """Set ``[section] key=value`` byte-precisely.

    Returns ``(new_text, previous_value_or_None, key_existed)``.

    Guarantees:

    * never creates a duplicate ``[section]`` header — when the section
      exists, the key is placed inside an existing occurrence;
    * when the key already exists (any ``[...]``-suffixed variant), the
      winning (last) assignment is rewritten in place and its suffix is
      preserved verbatim; every other byte is untouched;
    * when the section exists but the key does not, the key is appended
      at the end of the last occurrence of the section;
    * only when the section itself is missing is a new group appended
      at the end of the file.
    """
    lines = text.splitlines(keepends=True)
    section_headers: list[int] = []
    winning: int | None = None
    current: str | None = ""
    for index, line in enumerate(lines):
        stripped = line.strip()
        if _is_header(stripped):
            current = stripped[1:-1]
            if current == section:
                section_headers.append(index)
            continue
        if "=" in stripped and current == section:
            candidate, _, _ = stripped.partition("=")
            if _key_base(candidate) == key:
                winning = index

    previous: str | None = None
    if winning is not None:
        line = lines[winning]
        head, _, raw = line.strip().partition("=")
        previous = raw.strip()
        eol = "\r\n" if line.endswith("\r\n") else "\n"
        lines[winning] = f"{head.strip()}={value}{eol}"
        return "".join(lines), previous, True

    if section_headers:
        last_header = section_headers[-1]
        end = _section_end(lines, last_header)
        insert_at = end
        while insert_at > last_header + 1 and not lines[insert_at - 1].strip():
            insert_at -= 1
        lines.insert(insert_at, f"{key}={value}\n")
        return "".join(lines), previous, False

    prefix = "" if text.endswith("\n") or not text else "\n"
    return f"{text}{prefix}[{section}]\n{key}={value}\n", previous, False


def remove_ini_key(text: str, section: str, key: str) -> str:
    """Remove every ``key`` (including ``[...]``-suffixed variants) from
    every ``[section]`` occurrence; every other byte is preserved.

    A section header is never removed, even when its block becomes
    empty: the header itself is state this module does not own.
    """
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    current: str | None = ""
    for line in lines:
        stripped = line.strip()
        if _is_header(stripped):
            current = stripped[1:-1]
            out.append(line)
            continue
        if "=" in stripped and current == section:
            candidate, _, _ = stripped.partition("=")
            if _key_base(candidate) == key:
                continue
        out.append(line)
    return "".join(out)


# ---------------------------------------------------------------------------
# internals
# ---------------------------------------------------------------------------


def _is_header(stripped: str) -> bool:
    return stripped.startswith("[") and stripped.endswith("]")


def _key_base(key: str) -> str:
    """Key identity for matching: ``ColorScheme[$e]`` matches ``ColorScheme``."""
    return key.split("[", 1)[0].strip()


def _section_end(lines: list[str], header_index: int) -> int:
    """Index where the section block starting at ``header_index`` ends."""
    for index in range(header_index + 1, len(lines)):
        if _is_header(lines[index].strip()):
            return index
    return len(lines)
