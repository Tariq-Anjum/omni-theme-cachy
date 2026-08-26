# Session 8 — Security, Path Ownership, and Failure Injection

> Read `00_AGENT_EXECUTION_CONTRACT.md` and `00_PROJECT_MANIFEST.json` first.

## Agent Objective

Harden all filesystem writes and activation failure paths without changing the public architecture. Add deterministic tests for path safety, ownership, partial failure, and rollback.

## Scope

Inspect the existing path helpers, adapters, activation coordinator, state manager, and test fixtures. Reuse the current abstractions. Centralize validation rather than adding unrelated checks in individual callers.

## Required Behavior

Implement or verify the following:

- Canonicalize a path before validation.
- Resolve symlinks before writing.
- Reject relative traversal and absolute paths outside approved user-local roots.
- Reject sibling-prefix bypasses such as `/allowed-other` when `/allowed` is approved.
- Reject symlinks that escape an approved root.
- Reject unsafe ownership or permission states according to the existing project policy.
- Preserve the original configuration when a write fails.
- Roll back already-applied adapters when a later adapter fails.
- Return controlled, deterministic errors; never expose a traceback for expected CLI failures.

## Required Tests

Add table-driven tests for:

| Case | Expected result |
|---|---|
| Relative traversal | Rejected |
| Absolute path outside approved root | Rejected |
| Sibling-prefix path | Rejected |
| Symlink escaping approved root | Rejected |
| Missing parent directory | Controlled failure |
| Read-only destination | Controlled failure; original preserved |
| Failure in adapter 2 after adapter 1 succeeds | Adapter 1 rolled back |
| Rollback failure | Reported clearly; state marked unsafe if that is the existing contract |
| Malformed configuration | Original not overwritten |

Use temporary directories only. Do not test against the real home directory.

## Do Not Do

- Do not weaken existing validation to make a fixture pass.
- Do not add system-wide writes.
- Do not redesign the adapter contract.
- Do not add network-dependent tests.

## Commands

```bash
pytest -q
pytest -q tests -k 'path or security or rollback or failure'
git diff --check
```

Adapt test paths only when the repository uses different names.

## Acceptance Checklist

- [ ] Every filesystem write passes through the approved validator.
- [ ] Symlink escape and sibling-prefix attacks are covered by tests.
- [ ] Partial activation failure triggers rollback.
- [ ] Failed writes preserve the previous file.
- [ ] Full tests pass.
- [ ] No unrelated files changed.

## Final Response

Use the format in `00_AGENT_EXECUTION_CONTRACT.md` and stop after Session 8.
