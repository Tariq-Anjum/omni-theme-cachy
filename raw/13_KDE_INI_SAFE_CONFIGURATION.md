# Session 13 — KDE INI Configuration Safety and KWin/KDE State Preservation

## Objective

Eliminate raw string mutation of KDE INI-style configuration.

The goal is to prevent duplicated sections, malformed files, lost user settings, and unintended corruption.

## Scope

Audit:

```text
kwinrc
kdeglobals
konsolerc
plasmarc
other KDE .rc/.ini files touched by Omni
```

Do not rewrite files that Omni does not actually own.

## OpenCode tools

Use:

- `read`
- `glob`
- `grep`
- `bash`
- `edit`
- `write`
- `websearch`
- `webfetch`

Free/open-source:

```bash
rg
fd
fd
python
pytest
git
```

## Step 1 — Locate raw mutations

```bash
rg -n "\\[[A-Za-z0-9_:-]+\\]|write_text|open\\(|kwriteconfig|kreadconfig|configparser" core adapters hooks
```

Search specifically:

```bash
rg -n "kwinrc|kdeglobals|konsolerc|plasmarc" core adapters hooks
```

## Step 2 — Choose mechanism per file

Do not assume Python `configparser` is always the best option.

Preferred order:

1. KDE native configuration CLI/API if available and documented.
2. A dedicated parser that understands the file format.
3. `configparser` only when the file is genuinely compatible with its semantics.

This matters because KDE config files can have semantics that a generic INI parser may not preserve perfectly.

## Step 3 — Generic helper

If repeated safe INI operations exist, create:

```text
core/kde_config.py
```

Example:

```python
from pathlib import Path
import configparser

def set_ini_key(
    path: Path,
    section: str,
    key: str,
    value: str,
) -> None:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str

    if path.exists():
        parser.read(path, encoding="utf-8")

    if not parser.has_section(section):
        parser.add_section(section)

    parser.set(section, key, value)

    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        parser.write(handle, space_around_delimiters=False)

    tmp.replace(path)
```

Do not copy this blindly if the target file requires KDE-specific semantics.

## Step 4 — KWin helper

If code modifies a KWin setting, create a dedicated function such as:

```python
set_kwin_setting(...)
```

It must:

- read existing state;
- modify only the requested key;
- preserve unrelated keys;
- avoid duplicate sections;
- write atomically;
- participate in ownership/hash tracking;
- have rollback.

## Step 5 — Tests

Create:

```text
tests/unit/test_kde_config.py
tests/unit/test_kwin_config.py
```

Test:

```text
existing section
missing section
existing unrelated keys
existing target key
repeated application
rollback
format stability where required
no duplicate section
```

Example:

```python
def test_does_not_duplicate_windows_section(tmp_path):
    ...
```

## Step 6 — Verify ownership

If the setting is not necessary for the theme engine's core purpose, do not modify it merely to create a "seamless" experience.

The engine should avoid silently changing:

```text
window behavior
tiling behavior
KWin scripts
global workflow preferences
```

unless explicitly part of the product scope.

## Step 7 — KDE-native verification

Where possible use:

```bash
kreadconfig6 ...
kwriteconfig6 ...
```

only if actually installed.

Never fail just because one optional helper binary is absent.

## Exit condition

No code path that writes KDE INI-like configuration uses naive section appending.

## Commit

```bash
git add core adapters tests docs
git commit -m "fix: make KDE configuration writes section-safe and atomic"
```