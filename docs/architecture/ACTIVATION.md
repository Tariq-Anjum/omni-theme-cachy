# Activation — staging, promotion, failure policy, rollback

Implementation: `core/activation.py`, `core/state.py`, `core/staging.py`,
`core/filesystem.py`. The engine's central guarantee: **a failed switch can
never leave a half-applied theme.**

## Pipeline

```
resolve → merge overlay → validate → render → validate output
  → stage → inspect managed conflicts → snapshot current metadata
  → prepare new generation → atomically promote generation
  → materialize owned targets → apply adapters → verify
  → persist state
```

Lifecycle phases reported in outcomes: `CORE_STAGED`, `CORE_PROMOTED`,
`ADAPTERS_APPLIED`, `VERIFIED`. Final verdicts: `VERIFIED`, `DEGRADED`,
`FAILED`, `ROLLED_BACK`, `DRY_RUN`.

## Staging

Every application renders into a pristine
`~/.local/state/omni-theme/staging/` (leftovers from an aborted run are
wiped first). Nothing outside staging — nothing live on the desktop — is
touched during rendering. `manifest.json` in the staged tree records every
planned target with the SHA-256 of its rendered bytes; the staged tree is
re-hashed against that manifest before promotion (a tree that cannot trust
itself is never promoted).

## Generations and atomic promotion

The state layout is generations of *immutable* complete snapshots:

```
~/.local/state/omni-theme/
├── generations/gen-<UTC timestamp>-<pid>-<n>/   manifest.json + artifacts
├── current    -> generations/gen-…   (relative symlink)
├── previous   -> generations/gen-…   (rollback target)
├── staging/   ← scratch, rebuilt every run
├── backups/   ← adapter-level backups
└── state.json ← current/previous theme + generation, managed targets, adapters
```

Promotion swaps the `current` symlink atomically — a sibling temp symlink
is created and `os.replace`d over the real name (one same-filesystem
rename), so every reader sees either the old or the new generation.
Symlink targets stay *relative* so the whole tree is relocatable. Ordering
rule: `previous` is repointed at the outgoing generation **before**
`current` moves; a crash between the two swaps leaves both links on the
old generation — consistent, just not yet advanced.

The active generation is *never* mutated in place. A non-symlink occupying
`current`/`previous` is refused rather than silently replaced.

## Failure policy (encoded in `activate()`, never improvised by callers)

| Problem | Before any live mutation? | Outcome |
|---|---|---|
| load/validate/render failure | yes | `FAILED`, state untouched |
| managed-target conflict (no `--force`) | yes | `FAILED` naming every diverged target |
| core promotion/materialization failure | no | deterministic undo → `ROLLED_BACK` |
| adapter unsupported | — | skipped + reported; activation continues |
| non-critical adapter failure | — | outcome `DEGRADED`, processing continues |
| critical adapter failure (none shipped today) | — | deterministic rollback |

* An explicit `--force` is the only way past user-modified managed targets,
  and every forced overwrite is reported as a warning.
* Success is claimed only after byte-level verification (`sha256` read-back)
  of everything the engine wrote.
* **Idempotent short-circuit**: applying the already-active theme with
  identical rendered content keeps the current generation (no churn), still
  re-drives adapters as a health signal, and reports `VERIFIED`.

The undo path (`_undo_activation`) reverts pointers first, removes files
this attempt wrote that the prior state never owned, restores
previously-owned external files from the prior generation, then gives
adapters their rollback turn.

## Dry runs

`omni theme preview` / `omni theme apply --dry-run` execute the read-only
prefix of the pipeline against a temporary staging sandbox: manifests,
conflicts and adapter capabilities are reported, but no external file,
pointer or persisted state changes and no lifecycle events are emitted.

## Rollback

`omni theme rollback --yes` switches to the recorded `previous`
generation: swap pointers atomically, re-materialize the engine-owned
external targets from the previous manifest, re-apply the desktop state
(KDE adapter re-applies the scheme package and restores the journaled
wallpaper), then write metadata with current/previous exchanged. It
raises `RollbackError` (exit `ROLLBACK_FAILURE`) when there is nothing to
roll back to or the recorded generation vanished — the request can never
succeed, so callers must hear it loudly.

User-facing semantics: [../user/ROLLBACK.md](../user/ROLLBACK.md).
