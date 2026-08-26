# Session 13 — Safe KDE INI Configuration

> Read `00_AGENT_EXECUTION_CONTRACT.md` and `00_PROJECT_MANIFEST.json` first.

## Agent Objective

Make KDE INI updates safe, targeted, rollback-compatible, and preserving of unrelated configuration.

## Required Behavior

Use the repository's existing configuration abstraction where available. For each supported KDE INI file:

- Preserve unrelated sections and keys.
- Preserve comments and formatting when supported by the selected parser.
- Change only the required keys.
- Validate the destination through the centralized path validator.
- Create a rollback-safe snapshot before modification.
- Write atomically using a temporary file and replacement.
- Do not overwrite the original if parsing or writing fails.
- Use locking if the existing activation design supports concurrent CLI calls.

Identify exact files and keys from the current project code and tests. Do not guess KDE keys or introduce unrelated settings.

## Required Tests

- Existing unrelated values survive an update.
- Missing sections or keys are created safely when required.
- Malformed input is rejected without destroying the original.
- Atomic-write failure preserves the original.
- Reapplying the same values is idempotent.
- Rollback restores the exact prior content.

## Do Not Do

- Do not rewrite an entire configuration directory.
- Do not change desktop settings outside the documented contract.
- Do not use shell interpolation for file paths.
- Do not use the real user's KDE configuration in tests.

## Commands

```bash
pytest -q
pytest -q tests -k 'ini or kde or config or rollback'
git diff --check
```

## Acceptance Checklist

- [ ] Exact supported files and keys are documented.
- [ ] Unrelated configuration is preserved.
- [ ] Writes are atomic and rollback-compatible.
- [ ] Malformed input cannot destroy the original.
- [ ] Tests pass.

## Final Response

Use the format in `00_AGENT_EXECUTION_CONTRACT.md` and stop after Session 13.
