# Session 8: Security & Path Ownership

## Objective
Harden filesystem writes in the files listed in manifest.json. Add path validation and rollback tests.

## Rules
1. All paths must be canonicalized and resolved before use.
2. Reject paths outside the approved root.
3. Reject unsafe ownership per manifest.json.
4. Use atomic writes (write to .tmp, then rename).

## Acceptance
- [ ] Tests added for symlink escape and relative traversal.
- [ ] Partial failure triggers rollback.
- [ ] pytest -q passes.
- [ ] git commit and push.

STOP AND REPORT BLOCKED IF: You do not know the exact approved root directory. Do not guess. Do not re-read files to find it.
