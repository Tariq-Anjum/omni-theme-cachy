# Session 15 — One-Command Installation and CI

> Read `00_AGENT_EXECUTION_CONTRACT.md` and `00_PROJECT_MANIFEST.json` first.

## Agent Objective

Provide one documented, repeatable user-local installation path and CI coverage for the supported project behavior.

## Installation Contract

Use the repository's existing installer or create the smallest missing entry point. The documented golden path must:

1. Check prerequisites.
2. Install in user scope.
3. Install the CLI entry point and bundled assets.
4. Avoid protected system paths.
5. Be safe to run repeatedly.
6. Provide a dry-run mode if the installer changes filesystem state.
7. Report success or failure clearly.

Do not require root access. Do not silently modify shell startup files, system services, or unrelated desktop settings.

## CI Requirements

Use the existing CI provider and project conventions. Cover:

- Syntax or import validation.
- Unit and integration tests.
- Packaging or build validation.
- `git diff --check` equivalent.
- A supported Python or runtime version matrix only when justified by existing metadata.

Mock GUI and desktop commands in CI. Do not make CI depend on a running KDE session unless the repository already has a reliable headless strategy.

## Required Tests

- Installer help.
- Dry-run does not modify the filesystem.
- Clean user-local install.
- Repeated install is idempotent.
- CLI is available after installation.
- Uninstall or rollback behavior, if the project provides it.

## Do Not Do

- Do not add a second installer system.
- Do not run `sudo` in automated tests.
- Do not install into `/usr`, `/etc`, `/bin`, `/boot`, or `/var/lib`.
- Do not make optional KWin or OpenCode integrations mandatory.

## Commands

```bash
pytest -q
python -m build
<installer> --help
<installer> --dry-run
<project-cli> doctor
git diff --check
```

Run only commands supported by the repository and report unavailable tools.

## Acceptance Checklist

- [ ] One golden installation path is documented.
- [ ] Installation is user-local and repeatable.
- [ ] CI validates the actual supported project behavior.
- [ ] GUI operations are isolated or mocked in CI.
- [ ] Tests pass.

## Final Response

Use the format in `00_AGENT_EXECUTION_CONTRACT.md` and stop after Session 15.
