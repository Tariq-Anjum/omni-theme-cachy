# Session 9 — Documentation, Packaging, and Acceptance

> Read `00_AGENT_EXECUTION_CONTRACT.md` and `00_PROJECT_MANIFEST.json` first.

## Agent Objective

Make the project installable, understandable, and verifiable from a clean checkout while preserving the existing runtime behavior.

## Required Discovery

Read the current README, package metadata, CLI entry point, configuration examples, and CI files. Identify the project's actual package manager and test command before editing.

## Required Deliverables

Update or create only the documentation and packaging files needed for the existing architecture:

- Installation instructions.
- Development setup instructions.
- CLI usage reference.
- Configuration reference.
- Troubleshooting guide.
- Security and path-scope notes.
- Package metadata and console entry point, if missing.
- Clean-install acceptance test or documented reproducible procedure.

Every command in the documentation must be executable from a clean checkout or clearly marked as illustrative.

## Packaging Requirements

Support the project's existing installation model. If Python packaging is used, verify both:

```bash
python -m pip install .
python -m pip install -e .
```

Do not add a second packaging system. Do not require root access. Do not install into protected system paths.

## Acceptance Tests

Verify:

- A clean environment can install the package.
- The CLI entry point is available after installation.
- The documented preview, doctor, status, apply, and rollback commands match the implementation.
- Documentation does not claim unsupported platforms or features.
- Existing tests remain green.

## Do Not Do

- Do not redesign the CLI.
- Do not add undocumented dependencies.
- Do not copy generated build artifacts into source control unless the repository already requires them.
- Do not claim that a GUI integration works when only mocks were tested.

## Commands

```bash
pytest -q
python -m build
python -m pip install .
<project-cli> --help
<project-cli> doctor
<project-cli> status
git diff --check
```

Skip a command only when the corresponding tool or project convention does not exist, and report that fact.

## Acceptance Checklist

- [ ] Installation and development setup are documented.
- [ ] CLI and configuration references match the source.
- [ ] Packaging succeeds using the repository's chosen system.
- [ ] A clean-install smoke test passes.
- [ ] No unsupported claims remain.

## Final Response

Use the format in `00_AGENT_EXECUTION_CONTRACT.md` and stop after Session 9.
