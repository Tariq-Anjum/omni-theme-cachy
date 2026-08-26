# Session 14 — Agent CLI, `--yes`, and `commands.json`

> Read `00_AGENT_EXECUTION_CONTRACT.md` and `00_PROJECT_MANIFEST.json` first.

## Agent Objective

Make the CLI deterministic for both humans and AI agents, with explicit non-interactive behavior and a machine-readable command contract.

## Command Contract

Preserve existing command names. Document the actual names in the repository, using this behavior model:

| Operation | Default | `--yes` | Success exit code |
|---|---|---|---:|
| Preview | Non-interactive | No change | 0 |
| Doctor | Non-interactive | No change | 0 when healthy |
| Status | Non-interactive | No change | 0 |
| Apply | Ask for confirmation | Skip confirmation | 0 |
| Rollback | Ask for confirmation | Skip confirmation | 0 |

Use nonzero exit codes for invalid input, failed activation, failed rollback, and unhealthy diagnostics according to existing conventions.

## Implementation Requirements

- `--yes` must skip only confirmation prompts; it must not skip validation, backups, tests, or rollback logic.
- Piped or non-interactive execution must never hang waiting for input.
- Invalid commands and themes produce concise errors and nonzero exit codes.
- Output should be stable enough for an agent to parse.
- JSON output, if already supported, must remain valid and consistent.
- `commands.json` must describe the actual commands, arguments, effects, confirmation requirements, and exit behavior.

Use the existing CLI framework and schema conventions. Do not invent a parallel command system.

## Required Tests

- Confirmation accepted.
- Confirmation declined.
- `--yes` apply.
- `--yes` rollback.
- Non-interactive apply without `--yes` fails safely rather than hanging.
- Invalid command.
- Invalid theme.
- Adapter failure.
- Rollback failure.
- Machine-readable output, if supported.

## Do Not Do

- Do not bypass safety checks with `--yes`.
- Do not silently change existing command names.
- Do not print secrets or full environment data.
- Do not require a graphical session for CLI tests.

## Commands

```bash
pytest -q
<project-cli> --help
<project-cli> doctor
<project-cli> status
<project-cli> apply --help
<project-cli> rollback --help
git diff --check
```

Replace `<project-cli>` with the existing executable name discovered in the repository.

## Acceptance Checklist

- [ ] All commands have deterministic non-interactive behavior.
- [ ] `--yes` skips confirmation only.
- [ ] `commands.json` matches the implemented CLI.
- [ ] Failure and exit-code behavior is tested.
- [ ] Tests pass.

## Final Response

Use the format in `00_AGENT_EXECUTION_CONTRACT.md` and stop after Session 14.
