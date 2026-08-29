# Session 14 — Agent Ergonomics: `--yes`, `--json`, and `omni commands`

> Read `raw/00_AGENT_EXECUTION_CONTRACT.md` and `raw/00_PROJECT_MANIFEST.json` first — each exactly once. If output appears truncated, do NOT re-read; proceed with what you have or report BLOCKED naming the exact problem.

## Objective

Make Omni a predictable command-line API for AI agents and automation. OpenCode/Hermes-style agents should not need to parse human prose.

## Prior-art fact — read before implementing

Session 9 cross-verified the CLI surface against the parser. These flags ALREADY exist: `--yes`, `--dry-run`, `--force`, `--strict`, `--json`, `--root`, `--state-root`. This session audits coverage and consistency and fills gaps — it does not re-invent existing flags. `omni commands` may also already exist; Step 1 determines the actual state. If it exists, verify and extend it; do not create a second implementation.

## OpenCode tools

Use: read, glob, grep, bash, edit, write, lsp.
Free/open-source utilities: rg, fd, jq, python, pytest, git.

## Step 1 — Audit all mutating commands

    rg -n "def .*command|@.*command|theme apply|rollback|wallpaper set|write|modify|install" core/cli.py

Build a table:

    command | mutates? | --yes? | --dry-run? | --json? | confirmation?

Also record whether `omni commands` already exists and what it outputs.

## Step 2 — Consistent `--yes` on mutating commands

Ensure every mutating command exposes `--yes`. Do not add `--yes` to read-only commands just for consistency. If a flag already exists with the right semantics, reuse it; do not add a duplicate. If Click is used:

    def yes_option(function):
        return click.option(
            "--yes",
            is_flag=True,
            default=False,
            help="Skip confirmation prompts for automation.",
        )(function)

Apply to every mutating command that lacks it.

## Step 3 — Prevent prompt leaks

Tests must invoke commands with:

    runner.invoke(cli, ["theme", "apply", "default", "--yes"], input="")

and assert:
- no prompt
- no hang
- deterministic exit code

## Step 4 — JSON coverage

Ensure mutating and inspection commands support JSON when structured output is meaningful. Preferred:

    omni theme list --json
    omni theme current --json
    omni theme preview default --json
    omni theme apply default --dry-run --json
    omni status --json
    omni doctor --json

For a real apply, the supported shape is:

    omni theme apply default --yes --json

When `--json` is passed: keep stdout valid JSON; send all diagnostics, logs, and warnings to stderr. Tests use CliRunner with tmp fixtures; do not run the real-apply form against the real desktop as part of this session's verification.

## Step 5 — `omni commands`

If it does not exist, implement:

    omni commands
    omni commands --json

Example JSON:

    {
      "theme": ["list", "current", "apply", "validate", "preview", "rollback"],
      "wallpaper": ["list", "current", "set"],
      "doctor": null,
      "status": null,
      "version": null
    }

Also include machine-readable metadata where practical:

    {
      "name": "theme.apply",
      "mutates": true,
      "supports_yes": true,
      "supports_json": true,
      "supports_dry_run": true
    }

Prefer metadata over a minimal command-tree-only format because agents can decide whether an operation is safe. Keep this surface stable and documented — Session 17 (OpenCode integration) consumes it.

## Step 6 — Schema versioning

All JSON output from Omni includes:

    "schema_version": 1

Do not make agents infer schema versions from command output text. This applies to every JSON surface, including `omni commands --json` and `omni doctor --json`.

## Step 7 — Tests

Create tests/unit/test_cli_agent_ergonomics.py (follow the existing tests/ subdirectory conventions). Test:
- commands --json valid
- all mutating commands expose --yes
- apply --yes does not prompt (input="")
- dry-run + json is parseable
- stdout-only JSON (diagnostics on stderr)
- stable schema_version

## Step 8 — Verification

    pytest -q
    omni commands --json | jq .
    omni theme apply default --dry-run --yes --json | jq .
    omni doctor --json | jq .
    omni status --json | jq .

## Exit condition

An agent can safely discover:
- what commands exist
- which commands mutate
- which commands support dry-run
- which commands support JSON

without parsing `--help`.

## STOP / BLOCKED

Report BLOCKED and do not guess if:
- An existing flag or command conflicts with this session's requirements and resolving it would change an earlier session's public contract.
- A mutating command cannot safely support `--yes` without weakening a security check.
- The control plane and the code conflict and no higher-authority rule resolves it.

Do not invent a workaround silently.

## Completion

On PASS:
1. Update `raw/00_PROJECT_MANIFEST.json`: set `current_baseline` to "Session 14 completed", update `status`, remove `14` from `next_sessions`.
2. Update the README control-plane baseline line to Session 14.
3. Commit per AGENTS.md, then `git pull --rebase origin main`, then push.

## Commit

    git add core tests docs raw/00_PROJECT_MANIFEST.json README.md
    git commit -m "feat: add agent-friendly --yes and commands JSON API"
