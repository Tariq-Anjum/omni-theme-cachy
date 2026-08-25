"""JSONC-aware reading and surgical merging for VS Code settings.json.

VS Code's ``settings.json`` is **JSONC**: it may contain ``//`` and
``/* */`` comments and trailing commas. Two consequences drive this
module:

* Parsing for *reading* must tolerate those extensions
  (:func:`loads` strips them with a string-literal-aware scanner).
* Writing must never reformat the whole file — that would normalize
  unrelated user settings and destroy comments. Instead
  :func:`merge_property` performs byte-level surgery: it replaces only
  the value of one top-level property (or inserts one), leaving every
  other byte of the file untouched.

The scanner here is deliberately small and conservative. When anything
looks ambiguous (unterminated strings, unbalanced braces) the merge
functions fail with :class:`core.errors.AdapterError` rather than
guessing — a corrupt write to the user's settings file is unacceptable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from core.errors import AdapterError

__all__ = [
    "strip_jsonc",
    "loads",
    "TopLevelProperty",
    "scan_top_level_properties",
    "merge_property",
    "remove_keys_from_property",
    "remove_property",
    "safe_target",
]


def strip_jsonc(text: str) -> str:
    """Remove ``//`` and ``/* */`` comments and trailing commas.

    String literals are respected: comment markers inside quotes are
    preserved verbatim. Raises :class:`AdapterError` on unterminated
    strings so callers never parse half a file.
    """
    out: list[str] = []
    i, n = 0, len(text)
    in_string = False
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            end = text.find("*/", i + 2)
            if end == -1:
                raise AdapterError("unterminated block comment in JSONC input")
            i = end + 2
            continue
        out.append(ch)
        i += 1
    if in_string:
        raise AdapterError("unterminated string literal in JSONC input")
    return _strip_trailing_commas("".join(out))


def _strip_trailing_commas(text: str) -> str:
    """Drop commas directly followed by a closing ``}`` or ``]``."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == ",":
            j = i + 1
            while j < n and text[j] in " \t\r\n":
                j += 1
            if j < n and text[j] in "}]":
                i += 1
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def loads(text: str) -> dict:
    """Parse JSONC *text* into a dict; empty/whitespace-only → ``{}``.

    Raises :class:`AdapterError` (never :class:`json.JSONDecodeError`)
    so adapter code has one error type to handle. A root that is not an
    object is also an error: settings.json is always an object.
    """
    stripped = strip_jsonc(text)
    if not stripped.strip():
        return {}
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise AdapterError(f"settings.json is not valid JSONC: {exc}") from exc
    if not isinstance(parsed, dict):
        raise AdapterError("settings.json root must be a JSON object")
    return parsed


@dataclass(frozen=True)
class TopLevelProperty:
    """One ``"name": value`` pair at the root object level."""

    #: Byte span of the property name including its quotes.
    name_start: int
    name_end: int
    name: str
    #: Byte span of the value (after ``:``, up to but excluding ``,`` or ``}``).
    value_start: int
    value_end: int


def scan_top_level_properties(text: str) -> list[TopLevelProperty]:
    """Locate every top-level property of the root object in raw text.

    Works on the original bytes (comments intact). Returns properties in
    document order. A property's value span ends **at** its terminating
    comma (comma excluded) or includes its terminating ``}``/``]``
    (terminator included), so splicing ``[value_start:value_end]`` never
    loses structure. Raises :class:`AdapterError` when braces are
    unbalanced or a value cannot be skipped safely.
    """
    props: list[TopLevelProperty] = []
    i, n = 0, len(text)
    depth = 0
    pending_name: tuple[int, int, str] | None = None
    expecting_value = False

    def skip_string(start: int) -> int:
        j = start + 1
        while j < n:
            ch = text[j]
            if ch == "\\":
                j += 2
                continue
            if ch == '"':
                return j + 1
            j += 1
        raise AdapterError("unterminated string literal in settings.json")

    def skip_ws_and_comments(start: int) -> int:
        """Advance past whitespace and ``//…`` / ``/*…*/`` comments."""
        j = start
        while j < n:
            if text[j] in " \t\r\n":
                j += 1
            elif text[j] == "/" and j + 1 < n and text[j + 1] == "/":
                while j < n and text[j] != "\n":
                    j += 1
            elif text[j] == "/" and j + 1 < n and text[j + 1] == "*":
                end = text.find("*/", j + 2)
                if end == -1:
                    raise AdapterError("unterminated block comment in settings.json")
                j = end + 2
            else:
                return j
        return j

    def record(value_start: int, value_end: int) -> None:
        nonlocal pending_name, expecting_value
        assert pending_name is not None
        ns, ne, name = pending_name
        props.append(TopLevelProperty(ns, ne, name, value_start, value_end))
        pending_name = None
        expecting_value = False

    while i < n:
        ch = text[i]
        if ch == '"':
            end = skip_string(i)
            if depth == 1 and not expecting_value:
                j = skip_ws_and_comments(end)
                if j < n and text[j] == ":":
                    pending_name = (i, end, json.loads(text[i:end]))
                    expecting_value = True
            i = end
            continue
        if ch == "{":
            depth += 1
            i += 1
            continue
        if ch == "[":
            depth += 1
            i += 1
            continue
        if ch in "}]":
            depth -= 1
            if depth <= 0:
                # Root object closed. If we were mid-value, this brace is
                # what terminated the last property's scalar value.
                if expecting_value:
                    record(_value_start_after_colon(text, pending_name[1]), i)
                break  # root object closed
            if depth == 1 and expecting_value:
                # The value was an object/array: its closing bracket is
                # part of the value.
                record(_value_start_after_colon(text, pending_name[1]), i + 1)
            i += 1
            continue
        if ch == "," and depth == 1 and expecting_value:
            # Primitive/scalar value ended at the comma (excluded).
            record(_value_start_after_colon(text, pending_name[1]), i)
            i += 1
            continue
        i += 1

    if expecting_value:
        raise AdapterError("settings.json ends inside a property value")
    return props


def _value_start_after_colon(text: str, name_end: int) -> int:
    """First byte of a value: skip ``:``, whitespace and comments after the name."""
    j = name_end
    while j < len(text) and text[j] != ":":
        j += 1
    j += 1
    n = len(text)
    while j < n:
        if text[j] in " \t\r\n":
            j += 1
        elif text[j] == "/" and j + 1 < n and text[j + 1] in "/*":
            end = text.find("*/", j + 2) if text[j + 1] == "*" else -1
            if text[j + 1] == "/" :
                while j < n and text[j] != "\n":
                    j += 1
            elif end == -1:
                break  # let the parser report the malformed comment
            else:
                j = end + 2
        else:
            break
    return j


def merge_property(
    raw_text: str,
    name: str,
    value: dict,
) -> tuple[str, dict | None]:
    """Set top-level ``name`` to *value*, touching nothing else.

    Returns ``(new_text, previous_value)`` where *previous_value* is the
    parsed previous object (or ``None`` when the property did not
    exist). The replacement is byte-surgical: everything outside the one
    property's value span is preserved exactly, comments included.

    Only JSON-object values are supported (that is what settings use).
    """
    serialized = json.dumps(value, indent=4)

    if not raw_text.strip():
        # Missing or empty settings file: create a minimal object around
        # the property. This is the "empty configuration" path.
        return f"{{\n  \"{name}\": {serialized}\n}}\n", None

    props = scan_top_level_properties(raw_text)
    ours = next((p for p in props if p.name == name), None)

    if ours is None:
        return _insert_property(raw_text, name, serialized), None

    previous_raw = strip_jsonc(raw_text[ours.value_start : ours.value_end])
    try:
        previous = json.loads(previous_raw)
    except json.JSONDecodeError as exc:
        raise AdapterError(
            f"existing {name!r} value is not valid JSONC: {exc}"
        ) from exc
    if not isinstance(previous, dict):
        raise AdapterError(f"existing {name!r} value is not a JSON object")

    head = raw_text[: ours.value_start]
    tail = raw_text[ours.value_end :]
    new_text = f"{head}{serialized}{tail}"
    return new_text, previous


def remove_keys_from_property(
    raw_text: str,
    name: str,
    keys: tuple[str, ...],
) -> tuple[str, dict]:
    """Drop *keys* from top-level object ``name``, keeping others.

    Returns ``(new_text, removed_values)``. When the property becomes
    empty it is left as an empty object — removing the property line
    entirely would churn surrounding formatting for no benefit.
    Missing property / missing keys are fine (nothing removed).
    """
    props = scan_top_level_properties(raw_text)
    ours = next((p for p in props if p.name == name), None)
    removed: dict = {}
    if ours is None:
        return raw_text, removed

    previous_raw = strip_jsonc(raw_text[ours.value_start : ours.value_end])
    try:
        previous = json.loads(previous_raw)
    except json.JSONDecodeError as exc:
        raise AdapterError(
            f"existing {name!r} value is not valid JSONC: {exc}"
        ) from exc
    if not isinstance(previous, dict):
        raise AdapterError(f"existing {name!r} value is not a JSON object")

    remaining = {k: v for k, v in previous.items() if k not in set(keys)}
    removed = {k: v for k, v in previous.items() if k in set(keys)}
    if not removed:
        return raw_text, removed

    serialized = json.dumps(remaining, indent=4)
    head = raw_text[: ours.value_start]
    tail = raw_text[ours.value_end :]
    return f"{head}{serialized}{tail}", removed


def remove_property(raw_text: str, name: str) -> str:
    """Excise top-level ``name`` (and one adjacent comma) from the root.

    Whitespace/comments around the removed property are preserved. A
    missing property leaves the text untouched.
    """
    props = scan_top_level_properties(raw_text)
    for k, prop in enumerate(props):
        if prop.name != name:
            continue
        start, end = prop.name_start, prop.value_end
        if k + 1 < len(props):
            gap = raw_text[end : props[k + 1].name_start]
            comma = gap.find(",")
            if comma != -1:
                end += comma + 1
        elif k > 0:
            gap_start = props[k - 1].value_end
            gap = raw_text[gap_start:start]
            comma = gap.rfind(",")
            if comma != -1:
                start = gap_start + comma
        return raw_text[:start] + raw_text[end:]
    return raw_text


def safe_target(candidate: str | Path, base: str | Path) -> Path:
    """Reject *candidate* paths that escape *base* (path-traversal guard).

    Adapters compute destinations from fixed constants, but every
    computed path still passes through here so a future config mistake
    can never write outside the discovered application directory.
    """
    base_path = Path(base).expanduser().resolve()
    candidate_path = Path(candidate).expanduser()
    resolved = (
        candidate_path.resolve()
        if candidate_path.is_absolute()
        else (base_path / candidate_path)
    ).resolve()
    if base_path != resolved and base_path not in resolved.parents:
        raise AdapterError(
            f"path escapes application directory: {candidate_path} "
            f"is not under {base_path}"
        )
    return resolved


def _insert_property(raw_text: str, name: str, serialized_value: str) -> str:
    """Insert ``name: value`` into the root object without touching anything else."""
    stripped = strip_jsonc(raw_text)
    open_ = stripped.find("{")
    close = stripped.rfind("}")
    if open_ == -1 or close == -1 or close < open_ or stripped.strip()[0] != "{":
        raise AdapterError("settings.json root must be a JSON object")

    insertion_point = raw_text.rfind("}")
    if insertion_point == -1:
        raise AdapterError("settings.json root must be a JSON object")

    snippet = f'"{name}": {serialized_value}'
    between = stripped[open_ + 1 : close]
    if not between.strip():
        # Empty (or whitespace/comment-only) object: no leading comma.
        return f"{raw_text[:insertion_point]}{snippet}\n{raw_text[insertion_point:]}"
    # Non-empty: our entry needs a leading comma unless the raw text
    # immediately before the closing brace (ignoring whitespace and
    # comments) already has one.
    j = _skip_ws_and_comments_backwards(raw_text, insertion_point)
    needs_comma = j >= 0 and raw_text[j] != ","
    lead = ",\n  " if needs_comma else "\n  "
    return f"{raw_text[:insertion_point]}{lead}{snippet}\n{raw_text[insertion_point:]}"


def _skip_ws_and_comments_backwards(text: str, start: int) -> int:
    """Index of the last meaningful char before *start* (-1 at bof)."""
    i = start - 1
    while i >= 0:
        ch = text[i]
        if ch in " \t\r\n":
            i -= 1
            continue
        if i > 0 and text[i - 1] == "/" and ch == "/":
            # line comment: skip to its beginning
            line_begin = text.rfind("\n", 0, i)
            i = line_begin  # newline itself is whitespace; loop continues
            continue
        if i > 1 and text[i - 1 : i + 1] == "*/":
            begin = text.rfind("/*", 0, i - 1)
            if begin == -1:
                return i
            i = begin - 1
            continue
        return i
    return -1
