# Omni Theme Cachy — Agent Execution Contract

This contract is shared by Sessions 8–18. Read it before the selected session file.

## Mission

Complete the Omni Theme Cachy implementation without redesigning completed work. Make the smallest safe change that satisfies the selected session's acceptance criteria.

## Execution Rules

1. Work only in the repository checkout and only on the selected session.
2. Read the selected session and inspect existing code before editing.
3. Reuse existing abstractions, naming, error types, adapters, and test fixtures.
4. Do not introduce dependencies unless the session explicitly requires them.
5. Do not replace a working architecture with a new framework or rewrite unrelated code.
6. Do not proceed to a later session.
7. If a requirement conflicts with existing behavior, stop and report the conflict instead of guessing.
8. Never weaken security checks or bypass tests to obtain a passing result.
9. Preserve user data and existing configuration. Prefer atomic writes and rollback-safe operations.
10. Keep optional integrations optional; core activation must not depend on them.

## Required Discovery

Before editing, run only the minimum discovery needed:

```bash
pwd
git status --short
find . -maxdepth 2 -type f | sort
```

Then read the files named in the selected session. Search for existing symbols before creating replacements:

```bash
grep -R "class\|def\|def test_" -n src tests 2>/dev/null | head -200
```

Adapt paths if this repository uses a different source or test directory.

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
