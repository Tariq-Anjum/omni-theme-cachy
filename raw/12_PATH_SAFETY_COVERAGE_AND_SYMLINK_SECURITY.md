# Session 12 — Path Safety Coverage and Symlink Security

> Read `00_AGENT_EXECUTION_CONTRACT.md` and `00_PROJECT_MANIFEST.json` first.

## Agent Objective

Close remaining path-safety gaps and prove that every adapter cannot write outside approved user-local roots, including through symlinks.

## Required Design

Use one centralized path-validation function or service. Every adapter and file-writing helper must call it before writing.

The validator must:

- Resolve the intended destination against its approved root.
- Canonicalize existing path components.
- Safely handle missing final files and parent directories.
- Resolve symlinks where possible.
- Reject traversal, absolute escapes, sibling-prefix bypasses, and symlink escapes.
- Return a deterministic error suitable for CLI display.

Use path-aware comparisons such as `Path.is_relative_to()` or an equivalent safe implementation; do not use string-prefix checks.

## Required Tests

Cover:

- `..` traversal.
- Absolute outside paths.
- Approved path and similarly named sibling path.
- Symlinked file escaping the root.
- Symlinked parent escaping the root.
- Missing destination file inside an approved parent.
- Existing valid destination.
- Each adapter's actual write path.
- A symlink created or changed between validation and write, where the implementation can safely test it.

Use temporary directories and skip platform-specific symlink tests only with an explicit reported reason.

## Do Not Do

- Do not duplicate subtly different validation logic.
- Do not follow user-controlled symlinks outside approved roots.
- Do not use real system configuration in tests.
- Do not broaden approved roots to make tests pass.

## Commands

```bash
pytest -q
pytest -q tests -k 'path or symlink or security'
git diff --check
```

## Acceptance Checklist

- [ ] All file-writing code uses centralized validation.
- [ ] Symlink and sibling-prefix attacks are tested.
- [ ] Missing-file behavior is safe and deterministic.
- [ ] No protected system path is accepted.
- [ ] Full tests pass.

## Final Response

Use the format in `00_AGENT_EXECUTION_CONTRACT.md` and stop after Session 12.
