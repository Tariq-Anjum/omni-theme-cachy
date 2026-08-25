# Session 04 — Activation State, Atomic Promotion, Rollback, and Adapter Contract

## Objective

Build the core runtime state machine on top of the implementation produced by Session 03.

This session is the first place where rendered/staged theme output becomes a managed runtime state, but it must remain desktop-agnostic.

Do not implement KDE, GTK, VS Code, terminal, wallpaper, or KWin integration in this session.

The result must provide:

- explicit runtime state
- atomic current/previous promotion
- rollback
- ownership-aware target tracking
- adapter contract and capability reporting
- event lifecycle
- idempotent apply
- dry-run support at the engine/API level
- isolated tests

## Baseline and constraints

Session 03 is complete. Treat the actual repository as authoritative.

Before editing anything:

```bash
git status --short
git log --oneline -8
find core adapters hooks tests themes templates docs -maxdepth 3 -type f | sort
```

Do not recreate, rename, or replace Session 03 modules merely because an earlier plan expected different filenames.

### Current architectural invariant

```text
theme source
  -> loader/model/validation
  -> renderer
  -> staging
  -> activation
  -> adapter execution
  -> verification
```

The activation core must not import KDE-specific or application-specific code.

## OpenCode tool contract

Use OpenCode's built-in tools:

- `read` for named files and focused ranges
- `glob` for repository discovery
- `grep` for symbol/reference searches
- `bash` for tests, git, and safe system inspection
- `edit` for precise modifications
- `write` only for creating new files
- `lsp` where available for Python navigation/diagnostics
- `websearch`/`webfetch` only when current external behavior must be verified

Prefer free/open-source CLI tools available on CachyOS:

```bash
rg
fd
find
python
pytest
git
jq
```

Do not add a dependency just to obtain a feature already available from Python's standard library or existing project dependencies.

## Step 1 — Inspect Session 03 implementation

Read in full:

```text
core/theme_model.py
core/theme_loader.py
core/validation.py
core/renderer.py
core/staging.py
core/filesystem.py
core/targets.py
core/errors.py
core/cli.py
```

Also inspect:

```text
tests/
pyproject.toml
AGENTS.md
```

Use:

```bash
rg -n "stage|manifest|target|hash|write|replace|symlink|activate|rollback|event|adapter" core tests
```

Produce a short internal map before changing code:

```text
existing state primitives:
existing staging primitives:
existing target/manifest primitives:
existing error hierarchy:
existing CLI wiring:
missing pieces:
```

Do not write that map to the repo unless it is useful documentation.

## Step 2 — Define adapter contract

Create or extend the generic adapter contract without importing concrete adapters.

Preferred conceptual interface:

```python
from dataclasses import dataclass
from typing import Protocol

@dataclass(frozen=True)
class AdapterCapability:
    id: str
    supported: bool
    reason: str | None = None
    version: str | None = None

@dataclass(frozen=True)
class AdapterResult:
    adapter_id: str
    attempted: bool
    applied: bool
    verified: bool
    rolled_back: bool
    supported: bool
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

class ThemeAdapter(Protocol):
    id: str

    def capability(self, context) -> AdapterCapability: ...

    def plan(self, resolved_theme, context): ...

    def render(self, resolved_theme, staging, context): ...

    def apply(self, plan, context) -> AdapterResult: ...

    def verify(self, plan, context) -> AdapterResult: ...

    def rollback(self, previous_state, context) -> AdapterResult: ...
```

Adapt names to the existing code.

### Important semantic rule

Unsupported adapters are not failures.

Example:

```text
KDE            supported + applied
VS Code        supported + applied
GTK direct     unsupported
terminal       supported + applied
```

The overall theme activation may still succeed.

A real adapter failure is different:

```text
KDE             supported + apply failed
```

That distinction must exist in the state model.

## Step 3 — Implement runtime state

Create or adapt:

```text
core/state.py
core/activation.py
core/engine.py
core/events.py
```

Use XDG-aware locations:

```text
XDG_STATE_HOME/omni-theme/
    current/
    previous/
    staging/
    backups/
    state.json
```

Do not put runtime state in Git.

Represent at minimum:

```json
{
  "schema_version": 1,
  "current_theme": "default",
  "previous_theme": "tokyo-night",
  "activated_at": "...",
  "current_generation": "...",
  "previous_generation": "...",
  "managed_targets": [],
  "adapters": {}
}
```

Do not rely only on directory names. Store generation IDs and manifests.

## Step 4 — Atomic promotion

Required activation flow:

```text
resolve
  -> merge overlay
  -> validate
  -> render
  -> validate generated output
  -> stage
  -> inspect managed conflicts
  -> snapshot current metadata
  -> prepare new generation
  -> atomically promote generation
  -> apply adapters
  -> verify
  -> persist state
```

### Atomic filesystem rule

Do not replace the contents of the active generation in place.

Use:

```python
tmp_link = parent / ".current.new"
os.symlink(new_generation_dir, tmp_link)
os.replace(tmp_link, current_link)
```

If the implementation uses another atomic primitive, document why.

Never do:

```python
shutil.copytree(new, current, dirs_exist_ok=True)
```

for live promotion.

## Step 5 — Apply/verify failure semantics

Core state promotion and adapter application must not be confused.

Implement:

```text
CORE_STAGED
CORE_PROMOTED
ADAPTERS_APPLIED
VERIFIED
DEGRADED
FAILED
ROLLED_BACK
```

At minimum, expose a result object that tells the caller:

```text
core_changed
adapter_results[]
rollback_performed
warnings[]
errors[]
```

Policy:

- Core staging failure => no state change.
- Conflict => no live mutation unless explicit force policy exists.
- Core promotion failure => no new current state.
- Unsupported adapter => continue, report.
- Non-critical adapter failure => continue, mark degraded.
- Critical adapter failure => rollback according to adapter policy.
- Verification failure => rollback if the adapter declares itself critical.
- Never claim success merely because files were generated.

Make "critical adapter" explicit metadata, not an implicit exception path.

## Step 6 — Rollback

Implement:

```python
apply_theme(...)
rollback(...)
current_theme(...)
previous_theme(...)
status(...)
```

Rollback must:

1. verify previous generation still exists;
2. verify ownership metadata;
3. atomically switch current to previous generation;
4. restore only Omni-owned external files;
5. ask adapters to roll back where supported;
6. update metadata;
7. emit `post_rollback`.

Never revert arbitrary user files.

## Step 7 — Events

Implement internal events:

```text
pre_activate
post_core_activate
post_activate
post_verify
pre_rollback
post_rollback
```

The original plan only had three events. Keep those compatibility names where possible, but add the more precise lifecycle events if the implementation benefits from them.

Adapters should subscribe through an adapter registry/event dispatcher rather than being hard-coded in the core engine.

## Step 8 — Dry run API

Support:

```python
engine.apply(theme_name, dry_run=True)
```

Dry run must:

- resolve
- merge
- validate
- render
- validate outputs
- produce manifest
- detect conflicts
- report adapter capabilities
- avoid modifying external files
- avoid changing current/previous
- avoid emitting mutation events

Temporary staging may be created and cleaned.

## Step 9 — Tests

Create/extend isolated tests.

Required:

```text
tests/unit/test_state.py
tests/unit/test_activation.py
tests/unit/test_events.py
tests/unit/test_adapter_contract.py
```

Test:

- first activation with no previous state
- second activation
- repeated same-theme activation
- idempotency
- atomic promotion
- rollback
- missing previous generation
- stale previous generation
- unsupported adapter
- adapter failure
- adapter verification failure
- critical vs non-critical adapter
- dry run
- user-modified external target
- isolated XDG directories

No test may write to the real `$HOME`.

## Step 10 — Verification

Run:

```bash
python -m compileall core adapters hooks
pytest -q
python -m pytest -q
git diff --check
git status --short
```

Then inspect symlink behavior directly in a temporary directory.

## Exit condition

Session 04 is complete only when:

- runtime state exists outside Git;
- current/previous promotion is atomic;
- rollback is explicit and ownership-aware;
- adapter capabilities/results are represented;
- unsupported adapters do not falsely fail the core;
- critical adapter failures have deterministic rollback semantics;
- tests cover all of the above.

## Commit

```bash
git add core tests
git commit -m "feat: add activation state, atomic promotion, rollback, and adapter contract"
```

Do not push automatically unless the user explicitly asks or the session instruction below is being followed.

## Push prompt

If the repository workflow requires a push at the end:

```bash
git push origin main
```