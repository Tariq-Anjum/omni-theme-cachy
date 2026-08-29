# Rollback

Every `omni theme apply` builds an immutable **generation** — a complete
snapshot of rendered artifacts plus a manifest — and atomically swaps a
`current` symlink to it. The outgoing generation becomes `previous`.
Rollback swaps the pointers back and re-materializes engine-owned files
from the previous generation's manifest.

```
~/.local/state/omni-theme/
├── generations/gen-<timestamp>-<pid>-<n>/   immutable snapshots
├── current    -> generations/gen-…          active
├── previous   -> generations/gen-…          rollback target
└── state.json                               current/previous + managed hashes
```

## Usage

```bash
omni theme rollback --yes        # revert to the previous generation
omni status --json               # shows current_theme/previous_theme/generations
```

Without `--yes` on a non-interactive shell the command refuses (exit 2).
With nothing to roll back to, or a vanished previous generation, it exits
`ROLLBACK_FAILURE` with an explanatory error — never silently.

## What gets restored

| Kind | Rollback behaviour |
|---|---|
| Engine-owned generated files (`.colors`, Konsole scheme, …) | byte-exact from the previous generation's manifest (sha256-verified) |
| Color Scheme application on the desktop | the scheme package is re-applied via `plasma-apply-colorscheme` |
| Wallpaper | KDE adapter journal: the restored generation's theme wallpaper → most recent entry → recorded pre-Omni original; non-image selections are reported and left untouched |
| VS Code managed keys | previous values restored from the adapter journal (key-scoped) |
| Konsole profile key | previous `[Appearance] ColorScheme=` value (or key-absent) restored from the journal |
| GTK (kde-sync mode) | nothing to restore — KDE owns the sync; gtk adapter verifies |
| GTK (direct mode, opt-in) | managed CSS block removed/replaced from the gtk journal + backups |

## What rollback does *not* know about

1. **Manual changes made after the last apply.** If you switch color
   schemes in System Settings, Omni's `state.json` still records the
   generation it last activated. Rolling back re-applies *that*
   generation's scheme package — not your later manual choice. Manual
   desktop state (like a scheme you picked yourself) is outside Omni's
   knowledge by design: `kdeglobals` is KDE's state, not ours.
2. **Only one step.** `previous` is a single slot. Rolling back swaps
   current/previous, so a second `rollback` returns you to where you
   were (the two generations keep ping-ponging) — it is not a history
   stack.
3. **App-liveness differences.** Running apps repaint when KDE notifies
   them (Color Scheme does); some surfaces (GTK apps, occasionally
   plasmashell chrome) may need a restart to fully refresh — see
   `docs/research/KDE_PLASMA_6.md` for the verified reload table.

## Failed activations roll themselves back

If promotion, materialization or a **critical** adapter fails mid-run,
the engine performs the same undo (pointers reverted, foreign-to-prior
files removed, prior generation re-materialized, adapters given their
rollback turn) and reports `ROLLED_BACK` — or `FAILED` if even the undo
hit problems (details in `errors`). Unsupported adapters never trigger
rollback; they are skipped and reported, and the outcome is `DEGRADED`
at worst.

## Inspecting state safely

```bash
omni status --json | jq .consistent, .details   # pointer/state agreement
omni doctor --json | jq .managed_target_conflicts, .symlink_integrity
```

`state_consistent: false` means pointers and `state.json` disagree
(exit `CONFLICT`) — see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

To start over entirely (nuclear option): quit Omni, then remove
`~/.local/state/omni-theme/` and the engine-owned artifacts listed in
[OWNERSHIP_AND_SECURITY.md](../architecture/OWNERSHIP_AND_SECURITY.md).
Your own config files were never touched.
