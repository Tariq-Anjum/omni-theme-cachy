# Session 14 — Agent Ergonomics: `--yes`, `--json`, and `omni commands`

## Objective

Make Omni a predictable command-line API for AI agents and automation.

This is especially important because OpenCode/Hermes-style agents should not need to parse human prose.

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
jq
python
pytest
git
```

## Step 1 — Audit all mutating commands

```bash
rg -n "def .*command|@.*command|theme apply|rollback|wallpaper set|write|modify|install" core/cli.py
```

Create a table:

```text
command
mutates?
--yes?
--dry-run?
--json?
confirmation?
```

## Step 2 — Standardize `--yes`

If Click is used:

```python
def yes_option(function):
    return click.option(
        "--yes",
        is_flag=True,
        default=False,
        help="Skip confirmation prompts for automation.",
    )(function)
```

Apply to all mutating commands.

Do not add `--yes` to read-only commands just for consistency.

## Step 3 — Prevent prompt leaks

Tests should invoke commands with:

```python
runner.invoke(cli, ["theme", "apply", "default", "--yes"], input="")
```

and assert:

```text
no prompt
no hang
deterministic exit code
```

## Step 4 — JSON output contract

Ensure mutating and inspection commands support JSON when structured output is meaningful.

Prefer:

```text
omni theme list --json
omni theme current --json
omni theme preview default --json
omni theme apply default --dry-run --json
omni status --json
omni doctor --json
```

For a real apply:

```text
omni theme apply default --yes --json
```

Keep stdout valid JSON.

## Step 5 — `omni commands --json`

Implement:

```bash
omni commands
omni commands --json
```

Example JSON:

```json
{
  "theme": [
    "list",
    "current",
    "apply",
    "validate",
    "preview",
    "rollback"
  ],
  "wallpaper": [
    "list",
    "current",
    "set"
  ],
  "doctor": null,
  "status": null,
  "version": null
}
```

Also include machine-readable metadata where practical:

```json
{
  "name": "theme.apply",
  "mutates": true,
  "supports_yes": true,
  "supports_json": true,
  "supports_dry_run": true
}
```

Prefer metadata over a minimal command-tree-only format because agents can decide whether an operation is safe.

## Step 6 — Stable schema version

All JSON output from Omni should include:

```json
"schema_version": 1
```

Do not make agents infer schema versions from command output text.

## Step 7 — Tests

Create:

```text
tests/unit/test_cli_agent_ergonomics.py
```

Test:

```text
commands --json valid
all mutating commands expose --yes
apply --yes does not prompt
dry-run + json is parseable
stdout-only JSON
stable schema_version
```

## Step 8 — Verification

```bash
pytest -q
omni commands --json | jq .
omni theme apply default --dry-run --yes --json | jq .
omni doctor --json | jq .
omni status --json | jq .
```

## Exit condition

An agent can safely discover:

```text
what commands exist
which commands mutate
which commands support dry-run
which commands support JSON
```

without parsing `--help`.

## Commit

```bash
git add core tests docs
git commit -m "feat: add agent-friendly --yes and commands JSON API"
```