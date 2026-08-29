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

## Read Discipline

- Read each control-plane file exactly once per session.
- If any file's output appears truncated, empty, or incomplete, do NOT re-read it. Proceed with what you have, or report BLOCKED naming the exact problem.
- Never read the same control-plane file twice in one session.
- If a fact you need is not in the control plane or the code, report BLOCKED. Do not search the wider filesystem for it.

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

## Stop Condition
- A command would modify the real user's desktop or protected system paths, unless the selected session explicitly authorizes real-desktop verification (e.g., theme apply immediately followed by rollback).

```bash
pwd
git status --short
find core adapters tests templates themes scripts hooks docs -maxdepth 2 -type f | sort
