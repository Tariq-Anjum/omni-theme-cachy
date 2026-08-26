# Session 18 — Final Verification and Release Readiness

> Read `00_AGENT_EXECUTION_CONTRACT.md` and `00_PROJECT_MANIFEST.json` first.

## Agent Objective

Perform a deterministic release-readiness check for Sessions 1–17. Fix only release-blocking defects directly demonstrated by the verification commands.

## Preflight

```bash
git status --short
git diff --check
```

Review the diff for accidental files, secrets, protected-path changes, and undocumented dependencies.

## Required Verification Sequence

Run the commands supported by the repository in this order:

```bash
python -m compileall src
pytest -q
python -m build
<project-cli> --help
<project-cli> doctor
<project-cli> status
<project-cli> preview <known-theme>
<project-cli> apply --help
<project-cli> rollback --help
git diff --check
```

Use the actual source directory, build command, CLI name, and known fixture theme discovered in the repository. Do not run real activation against the user's desktop unless an isolated test environment is explicitly provided.

## Release Checklist

- [ ] All tests pass.
- [ ] Packaging succeeds.
- [ ] CLI help and diagnostics work.
- [ ] Preview is non-destructive.
- [ ] Apply and rollback expose the expected confirmation behavior.
- [ ] Security and symlink tests pass.
- [ ] Optional integrations remain optional.
- [ ] Documentation matches the implementation.
- [ ] No secrets or generated artifacts were added.
- [ ] No protected system paths are modified.
- [ ] Working tree contains only intentional changes.

## Defect Policy

Fix only defects that block the checklist or violate an explicit earlier-session contract. If a broader improvement is discovered, report it as a follow-up instead of expanding scope.

## Final Report

Return exactly:

```text
Status: PASS or BLOCKED

Verification:
- command — PASS or FAIL

Release blockers:
- None, or exact blocker with failing command

Follow-up notes:
- None, or concise non-blocking observations
```

Do not create a release, tag, commit, or push changes in this session.
