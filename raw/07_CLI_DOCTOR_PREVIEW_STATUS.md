# Session 07 — CLI Product Layer: Commands, Doctor, Preview, Status, JSON, and Exit Codes

## Objective

Turn the engine into an automation-friendly CLI product.

This session establishes the command contract that both humans and coding agents will consume.

## OpenCode tools

Use:

- `read`
- `glob`
- `grep`
- `bash`
- `edit`
- `write`
- `lsp`

Use free/open-source commands:

```bash
rg
fd
jq
python
pytest
git
```

Do not introduce a CLI framework solely to replace an existing working one.

## Step 1 — Read current CLI

Read:

```text
core/cli.py
pyproject.toml
core/engine.py
core/state.py
core/activation.py
```

Map existing command names before adding anything.

## Step 2 — Canonical command tree

The target CLI is:

```text
omni
├── theme
│   ├── list
│   ├── current
│   ├── apply <name>
│   ├── validate <name>
│   ├── preview <name>
│   └── rollback
├── wallpaper
│   ├── list
│   ├── current
│   └── set <path>
├── status
├── doctor
└── version
```

Do not remove existing compatible commands without a migration reason.

## Step 3 — Write safety convention

Every command that can mutate state must support a non-interactive option.

Canonical:

```text
--yes
```

Keep `--apply` only if an existing command already depends on that convention; document aliases rather than creating inconsistent behavior.

Defaults should be safe:

```text
preview/validate = read-only
apply = confirmation unless --yes
rollback = confirmation unless --yes
wallpaper set = confirmation unless --yes
```

A dry-run should be available where useful.

## Step 4 — Machine-readable mode

Where structured output exists:

```text
--json
```

must emit JSON only.

No progress text.

No warning prose mixed into stdout.

Use stderr for human diagnostics if appropriate.

Define stable top-level schemas.

Example:

```json
{
  "schema_version": 1,
  "command": "theme.preview",
  "ok": true,
  "theme": {},
  "adapters": [],
  "targets": [],
  "warnings": []
}
```

## Step 5 — Exit codes

Define constants:

```python
class ExitCode(IntEnum):
    SUCCESS = 0
    USAGE = 2
    VALIDATION_ERROR = 10
    CONFLICT = 11
    UNSUPPORTED = 12
    ACTIVATION_FAILURE = 13
    ROLLBACK_FAILURE = 14
    INTERNAL_ERROR = 20
```

Use fewer values if the existing CLI framework has a better established pattern.

Document them.

## Step 6 — Doctor

Implement:

```bash
omni doctor
omni doctor --json
```

Check:

```text
OS
desktop
Plasma version
session type
Python version
required binaries
XDG directories
runtime directory
theme directories
write permissions
current/previous state
symlink integrity
managed target conflicts
adapter capabilities
KDE Color Scheme availability
wallpaper capability
GTK synchronization path
```

Do not change anything during doctor.

## Step 7 — Preview

Implement:

```bash
omni theme preview <name>
omni theme preview <name> --json
```

Preview performs:

```text
resolve
merge
validate
render
target planning
adapter capability planning
```

but does not:

```text
write live targets
change current
change previous
apply KDE settings
change wallpaper
dispatch mutation events
```

Display:

```text
theme
mode
semantic palette
surface roles
gradients
wallpaper
adapters
generated targets
conflicts
warnings
```

## Step 8 — Status

Implement:

```bash
omni status
omni status --json
```

Show:

```text
current theme
previous theme
generation
activation timestamp
adapter statuses
managed targets
conflicts
degraded state
```

## Step 9 — Version

Expose:

```bash
omni version
```

Include package version and schema version where useful.

## Step 10 — Help consistency

Every command must have:

- description
- examples
- write/read classification
- `--yes` if mutating
- `--json` if output can be represented safely

## Step 11 — Tests

Create/extend CLI tests:

```text
tests/unit/test_cli_commands.py
tests/unit/test_cli_json.py
tests/unit/test_cli_exit_codes.py
tests/unit/test_cli_doctor.py
tests/unit/test_cli_preview.py
tests/unit/test_cli_status.py
```

Use Click's test runner if Click is already the project framework.

Test that JSON output can be parsed:

```python
data = json.loads(result.output)
assert data["schema_version"] == 1
```

## Step 12 — Verification

```bash
pytest -q
python -m compileall core adapters
python -m omni --help  # or the project's actual invocation
omni theme list
omni theme preview default --json | jq .
omni doctor --json | jq .
omni status --json | jq .
git diff --check
```

## Exit condition

A new user or agent can:

- discover themes
- validate a theme
- preview a theme
- apply safely
- inspect status
- diagnose environment
- rollback

without parsing uncontrolled human text.

## Commit

```bash
git add core tests docs
git commit -m "feat: build automation-friendly omni CLI with doctor and preview"
```
