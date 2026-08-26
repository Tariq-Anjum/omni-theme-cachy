# Session 11 — GTK Integration with KDE Synchronization

> Read `00_AGENT_EXECUTION_CONTRACT.md` and `00_PROJECT_MANIFEST.json` first.

## Agent Objective

Complete GTK integration while keeping KDE Plasma as the primary theme source and preserving transactional activation behavior.

## Synchronization Contract

Use this model unless the existing project contract explicitly says otherwise:

- KDE Plasma is the primary theme source.
- GTK configuration is derived from the active Omni theme.
- Applying a theme updates KDE and GTK as one activation transaction.
- A GTK failure follows the existing rollback contract.
- Manual GTK changes are not imported automatically.
- GTK integration remains optional when GTK is unavailable.

Before editing, confirm the actual GTK 2, GTK 3, and GTK 4 targets supported by the repository. Do not add support merely because a version exists.

## Implementation

1. Reuse the existing adapter interface.
2. Map the existing theme model to the supported GTK configuration files.
3. Stage changes before activation.
4. Use centralized path validation.
5. Preserve unrelated configuration.
6. Add mocked tests for absent GTK, successful synchronization, malformed configuration, and partial failure.

## Required Tests

- GTK unavailable does not break core KDE activation.
- Successful activation updates all supported GTK targets.
- Unrelated GTK settings remain unchanged.
- GTK write failure causes the expected rollback.
- Reapplying the same theme is idempotent.

## Do Not Do

- Do not modify KDE behavior outside the adapter contract.
- Do not require a running graphical session in unit tests.
- Do not overwrite complete configuration files when a targeted update is sufficient.
- Do not introduce a new configuration format.

## Commands

```bash
pytest -q
pytest -q tests -k 'gtk or kde or sync or adapter'
git diff --check
```

## Acceptance Checklist

- [ ] Supported GTK targets are explicitly identified.
- [ ] KDE remains the source of truth.
- [ ] GTK failure is rollback-safe.
- [ ] Missing GTK is handled according to the optional-integration policy.
- [ ] Tests pass without requiring a real desktop session.

## Final Response

Use the format in `00_AGENT_EXECUTION_CONTRACT.md` and stop after Session 11.
