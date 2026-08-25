# Session 12 — Path Safety Coverage and Symlink-Safe Writes

## Objective

Prove that every filesystem write path is protected by the central filesystem policy.

Session 08 audited security conceptually. This session turns that into measurable coverage.

## OpenCode tools

Use:

- `read`
- `glob`
- `grep`
- `bash`
- `edit`
- `write`
- `lsp`

Free/open-source utilities:

```bash
rg
fd
python
pytest
git
```

## Step 1 — Identify the actual security primitive

Read:

```text
core/filesystem.py
core/staging.py
```

Find the real function(s) responsible for safe target resolution.

Do not rename working APIs solely to match this prompt.

Document:

```text
function name
signature
root semantics
symlink semantics
exception type
```

## Step 2 — Enumerate writes

Run:

```bash
rg -n --glob '*.py' \\
  "write_text|write_bytes|open\\\\(|Path\\\\(|os\\.replace|os\\.rename|os\\.symlink|shutil\\.copy|shutil\\.copy2|shutil\\.copytree" \\
  core adapters hooks scripts
```

Build a review table internally:

```text
file
operation
target source
expected root
guard
ownership
test
```

## Step 3 — Guard every external target

Every write outside an internally created temporary directory must have:

```text
trusted root
validated candidate
ownership decision
atomic write strategy
```

Examples:

```text
~/.local/share/color-schemes
~/.config/Code/User
~/.local/state/omni-theme
wallpaper cache
terminal profile directory
KDE user data
```

## Step 4 — Symlink attack cases

Test:

```text
target is symlink to allowed file
target is symlink to outside root
parent directory is symlink
candidate resolves outside root
broken symlink
dangling path that later becomes a symlink
```

Use an isolated tmp directory.

## Step 5 — Atomic write helper

If the project does not already have one, centralize:

```python
def atomic_write_text(path: Path, content: str, *, mode: int | None = None) -> None:
    ...
```

Required behavior:

```text
validate path
create temp sibling
write
flush
fsync where appropriate
replace atomically
preserve intended permissions
```

Do not make callers repeat security logic.

## Step 6 — Regression tests

Create:

```text
tests/security/test_write_path_coverage.py
tests/security/test_symlink_escape.py
tests/security/test_atomic_write.py
```

Tests must assert traversal attempts fail.

Do not use vague:

```python
pytest.raises(Exception)
```

when a precise project exception exists.

## Step 7 — Static heuristic

Create:

```text
scripts/audit_write_paths.py
```

It may use Python AST to list direct writes.

Do not claim AST detection proves security.

The script's purpose is reviewer assistance.

Example:

```python
WRITE_ATTRS = {
    "write_text",
    "write_bytes",
}

OPEN_MODES = {"w", "wb", "a", "ab"}

# Walk AST and print candidate writes for manual review.
```

## Step 8 — Run

```bash
python scripts/audit_write_paths.py
pytest -q
python -m compileall core adapters hooks scripts
git diff --check
```

## Exit condition

All external writes are either:

- centrally guarded;
- inside controlled staging/temp directories;
- or explicitly documented as a native system operation that has its own safety/ownership contract.

## Commit

```bash
git add core tests scripts docs
git commit -m "test: enforce path and symlink safety across all write paths"
```