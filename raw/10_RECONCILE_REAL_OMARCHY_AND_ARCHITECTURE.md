# Session 10 — Omarchy Compatibility Reconciliation

> Read `00_AGENT_EXECUTION_CONTRACT.md` and `00_PROJECT_MANIFEST.json` first.

## Agent Objective

Compare the existing Omni Theme Cachy behavior with the project's stated Omarchy compatibility requirements and implement only demonstrated gaps.

## Strict Scope

This is a compatibility audit, not a rewrite.

- Do not replace the current architecture.
- Do not copy Omarchy implementation code.
- Do not add undocumented Omarchy dependencies.
- Do not change completed behavior without a failing acceptance test.
- Do not convert optional behavior into a core dependency.

## Procedure

1. Read the current architecture and completed-session tests.
2. Extract the compatibility requirements already documented in the repository.
3. Build a small table with: requirement, current behavior, gap, minimal change, and proving test.
4. Implement only rows with a confirmed gap.
5. Add regression tests for every change.

## Required Compatibility Checks

Verify the documented behavior for:

- Theme model and color resolution.
- Template rendering and staging.
- Activation, state capture, and rollback.
- KDE Plasma integration.
- GTK, VS Code, and terminal adapters.
- CLI preview, doctor, status, apply, and rollback.
- User-local path and security boundaries.

If a requirement is ambiguous or not represented by an existing test, stop and report it instead of guessing.

## Commands

```bash
pytest -q
pytest -q tests -k 'theme or activation or adapter or cli'
git diff --check
```

## Acceptance Checklist

- [ ] A compatibility table exists in the final report or project documentation.
- [ ] Every implementation change is tied to a documented gap.
- [ ] No architecture rewrite or new undocumented dependency was introduced.
- [ ] Regression tests prove each compatibility fix.
- [ ] Full tests pass.

## Final Response

Use the format in `00_AGENT_EXECUTION_CONTRACT.md` and stop after Session 10.
