# Omni Theme Cachy — Agent Execution Contract

This contract is shared by Sessions 8–18. Read it before the selected session file.

## Control-Plane Authority

The execution control plane lives under `raw/`.

Authority order:

1. `raw/00_PROJECT_MANIFEST.json` — repository baseline, execution status, verified facts, blockers, and session dependencies.
2. `raw/00_AGENT_EXECUTION_CONTRACT.md` — global execution rules and safety invariants.
3. `raw/<session>.md` — acceptance criteria for the selected session.
4. Source code and tests — implementation evidence.
5. `README.md` and other descriptive documentation — useful context, but not authoritative for execution state.

If these sources conflict, stop and report the conflict unless the higher-authority source explicitly resolves it.

## Mission

Complete the Omni Theme Cachy implementation without redesigning completed work. Make the smallest safe change that satisfies the selected session's acceptance criteria.

## Required Preflight

Before reading or editing the selected session:

1. Read `raw/00_PROJECT_MANIFEST.json`.
2. Confirm the selected session is allowed by `current_baseline`, `next_sessions`, and `session_dependencies`.
3. Read this contract.
4. Read the selected session file.
5. Inspect the existing implementation named by the selected session.

Do not infer execution state from README status text when the raw control plane provides a value.

## Repository Layout

This repository uses a top-level module layout:

- `core/` — core implementation.
- `adapters/` — KDE, GTK, Konsole, and VS Code adapters.
- `tests/` — unit and integration tests.
- `templates/` — templates.
- `themes/` — theme assets.
- `scripts/` — project scripts.
- `hooks/` — project hooks.
- `docs/` — documentation.
- `raw/` — execution control plane and session records.

Do not reinterpret this project as a `src/`-layout repository.

## Execution Rules

1. Work only in the repository checkout and only on the selected session.
2. Read the selected session and inspect existing code before editing.
3. Reuse existing abstractions, naming, error types, adapters, and test fixtures.
4. Do not introduce dependencies unless the session explicitly requires them.
5. Do not replace a working architecture with a new framework or rewrite unrelated code.
6. Do not proceed to a later session.
7. If a requirement conflicts with existing behavior or a higher-authority control-plane record, stop and report the conflict instead of guessing.
8. Never weaken security checks or bypass tests to obtain a passing result.
9. Preserve user data and existing configuration. Prefer atomic writes and rollback-safe operations.
10. Keep optional integrations optional; core activation must not depend on them.

## Required Discovery

Before editing, run only the minimum discovery needed:

```bash
pwd
git status --short
find core adapters tests templates themes scripts hooks docs -maxdepth 2 -type f | sort
```

Read the control-plane files directly by path; do not substitute broad repository discovery for them.

Then read the files named in the selected session. Search only the verified project directories for existing symbols before creating replacements:

```bash
grep -R "class\|def\|def test_" -n core adapters tests | head -200
```

Do not perform broad repository discovery unless a file or symbol explicitly required by the selected session is missing.

## Change Discipline

- Modify only files required by the selected session.
- Add regression tests for every new behavior or failure mode.
- Keep public APIs backward-compatible unless the session explicitly changes them.
- Use clear, deterministic error messages.
- Avoid network access, destructive commands, and system-wide changes during tests.
- Do not run installation commands requiring root unless the session explicitly defines a safe test fixture.

## Verification

Run the exact commands in the session file. At minimum, run the project's existing test command if one is available. Also run:

```bash
git diff --check
```

A session is complete only when all acceptance criteria pass, tests are added or updated, and the working tree contains no accidental changes.

## Stop Conditions

Stop immediately and report `BLOCKED` if:

- Required files or symbols do not exist.
- A test exposes a conflict with an earlier session.
- A security decision is unspecified.
- The control-plane records conflict and no higher-authority rule resolves the conflict.
- A command would modify the real user's desktop or protected system paths.
- A test fails for an unrelated pre-existing reason and cannot be isolated.

Do not invent a workaround silently.

## Final Response Format

Return only:

```text
Status: PASS or BLOCKED

Changed files:
- path — one-line purpose

Commands run:
- command — PASS or FAIL

Tests:
- test result summary

Blockers:
- None, or exact unresolved issue
```
