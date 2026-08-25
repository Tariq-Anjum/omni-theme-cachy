# Session 08 — Security Hardening, Path Policy, Ownership, Failure Injection, and QA

## Objective

Perform a security and correctness audit over the implementation built in Sessions 01–07.

This is a hardening session, not a feature-expansion session.

Do not add unrelated features.

## Security invariant

```text
theme data != executable code
```

Never execute arbitrary commands from theme TOML, templates, filenames, or user overlays.

Never automatically execute third-party hooks.

## OpenCode tools

Use:

- `read`
- `glob`
- `grep`
- `bash`
- `edit`
- `write`
- `lsp`
- `websearch`/`webfetch` only for security behavior that depends on current platform documentation

Free/open-source tools:

```bash
rg
fd
find
python
pytest
git
jq
```

If the repo already uses:

```bash
ruff
mypy
bandit
```

run them. Do not add them merely for this session unless the project already chose them.

## Step 1 — Inventory every write path

Run:

```bash
rg -n "write_text|write_bytes|open\\([^\\n]*['\"]w|os\\.replace|os\\.rename|os\\.symlink|shutil\\.copy|shutil\\.copy2|shutil\\.copytree|mkdir\\(" core adapters hooks scripts
```

Then inspect every result.

Classify:

```text
internal staging write
managed user target
runtime state
cache
temporary file
system path
unknown
```

Unknown paths must be reviewed manually.

## Step 2 — Central path policy

Read `core/filesystem.py` in full.

Use the actual function name implemented in Session 03/04.

Do not assume `safe_under()` exists.

The central policy should support:

```python
safe_under(root, candidate)
```

or the repository's equivalent.

Required properties:

- resolves symlink-aware paths appropriately;
- rejects traversal outside allowed roots;
- rejects unexpected absolute paths;
- handles nonexistent final targets;
- does not accidentally approve `root/../root-evil`;
- does not follow attacker-controlled symlink escapes.

Prefer `Path.resolve(strict=False)` plus explicit containment checks where appropriate.

## Step 3 — Regression tests

Create:

```text
tests/security/test_path_policy.py
tests/security/test_write_coverage.py
```

Test:

```text
../../etc/passwd
absolute unrelated path
symlink escape
nested legal path
nonexistent legal target
user-home legal target where specifically permitted
```

## Step 4 — Target ownership

Every externally managed target should have a manifest record:

```json
{
  "target": "...",
  "adapter": "kde",
  "owner": "omni",
  "generation": "...",
  "sha256": "...",
  "previous_sha256": "..."
}
```

Before overwrite:

```text
current hash == Omni recorded hash
    -> safe

current hash != Omni recorded hash
    -> conflict

target missing
    -> recreate if ownership permits
```

Never silently overwrite user changes.

## Step 5 — User overlays and templates

Audit:

```text
theme path
overlay path
template path
template output
wallpaper path
target path
```

No user-controlled path may escape its intended root.

Do not evaluate template contents as Python, shell, Jinja execution, or arbitrary code.

If the template system supports only the project's explicit helper syntax, keep it that way.

## Step 6 — Archive handling

If archive import/extraction exists anywhere:

- reject absolute paths
- reject `..`
- reject symlink escapes
- extract into a temporary directory
- verify all final paths remain under extraction root
- only then promote files

If archive import does not exist, document that no archive extraction code is in scope.

## Step 7 — Subprocess safety

Run:

```bash
rg -n "subprocess\\.|os\\.system|shell=True|Popen\\(|run\\(" core adapters hooks scripts
```

For every subprocess:

- prefer argument arrays;
- `shell=False`;
- fixed executable names;
- no TOML-derived command fragments;
- validate executable presence;
- return structured errors.

Any `shell=True` must have a compelling, documented reason.

## Step 8 — Hook safety

Hooks must be internal events, not executable strings from theme data.

If user hooks are intentionally supported later, they need a separate trust model and explicit opt-in.

Do not implement arbitrary hooks in this session.

## Step 9 — Failure injection

Test:

```text
invalid TOML
invalid color
invalid gradient
missing template
generated output invalid
missing KDE command
wallpaper failure
target manually modified
adapter failure
verification failure
missing current symlink
missing previous symlink
broken symlink
interrupted promotion
disk-full-like write failure where practical
```

After failures, assert:

```text
previous valid state remains recoverable
current does not reference partial data
no unrelated files changed
```

## Step 10 — Idempotency

Run repeatedly in an isolated environment:

```bash
omni theme apply default --yes
omni theme apply default --yes
omni theme apply default --yes
```

Verify:

- no duplicated content
- no growing config
- stable generation semantics where intended
- no corrupted symlinks
- no accumulating temporary files

## Step 11 — KDE config corruption audit

Search:

```bash
rg -n "\\[Windows\\]|\\[General\\]|kreadconfig|kwriteconfig|configparser|\\.rc" core adapters hooks
```

Any KDE `.rc` file mutation must use an INI-aware approach or a KDE-native configuration tool, not naive string appending.

Do not blindly replace KDE config files with Python `configparser` if doing so loses semantics unsupported by `configparser`; Session 13 will perform the dedicated audit.

## Step 12 — QA

Run:

```bash
pytest -q
python -m compileall core adapters hooks
git diff --check
git status --short
git diff
git log --oneline --decorate -20
```

Remove:

```text
debug artifacts
temporary files
secrets
generated personal config
caches
untracked runtime state
```

## Exit condition

No known critical security/correctness issue remains around:

- filesystem paths
- ownership
- arbitrary execution
- template handling
- subprocesses
- rollback
- atomic promotion
- failure recovery

## Commit

```bash
git add core adapters hooks tests scripts docs
git commit -m "test: harden paths, ownership, subprocesses, and failure recovery"
```