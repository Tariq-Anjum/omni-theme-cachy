# Session 16 — Optional KWin Scripts and Scope Hygiene

> Read `00_AGENT_EXECUTION_CONTRACT.md` and `00_PROJECT_MANIFEST.json` first.

## Agent Objective

Keep KWin script support isolated and optional without affecting core theme activation, preview, doctor, status, apply, or rollback.

## Required Behavior

- Detect whether KWin scripting is available.
- Keep the feature disabled unless explicitly enabled by the user or existing configuration.
- Do not fail core operations when KWin scripting is unavailable.
- Validate all script paths through the central path-safety service.
- Install or update only the documented KWin script files.
- Preserve rollback behavior and avoid unrelated KWin configuration changes.

## Required Tests

- KWin unavailable.
- Feature disabled.
- Feature enabled and installation succeeds.
- Invalid or escaping script path.
- Script installation failure.
- Core activation remains successful when the optional feature fails or is absent.
- Repeated installation is idempotent.

## Do Not Do

- Do not make KWin scripts a core dependency.
- Do not install scripts automatically without explicit enablement.
- Do not modify unrelated KWin settings.
- Do not require a live desktop session in unit tests.

## Commands

```bash
pytest -q
pytest -q tests -k 'kwin or optional or script'
git diff --check
```

## Acceptance Checklist

- [ ] KWin support is clearly optional.
- [ ] Core functionality works without KWin.
- [ ] Script paths are safely validated.
- [ ] Failure behavior is tested and documented.
- [ ] Tests pass.

## Final Response

Use the format in `00_AGENT_EXECUTION_CONTRACT.md` and stop after Session 16.
