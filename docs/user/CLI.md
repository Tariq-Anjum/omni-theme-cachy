# CLI Reference

`omni` (alias `omni-theme`) is the automation-friendly command surface.
Everything a script or coding agent needs is parseable: exit codes are
stable, structured commands emit JSON only, and every mutating command
is gated by `--yes` in non-interactive shells.

## Command tree

```
omni
├── theme
│   ├── list                                # read
│   ├── current                             # read
│   ├── apply <name> [--yes] [--dry-run] [--force]   # write
│   ├── create --from-wallpaper <img> --name <n> [--apply --yes]   # write
│   ├── validate <name> [--strict]          # read
│   ├── preview <name>                      # read
│   └── rollback [--yes]                    # write
├── wallpaper
│   ├── list                                # read
│   ├── current                             # read
│   └── set <path> [--yes]                  # write
├── status                                  # read
├── doctor                                  # read
├── version                                 # read
└── commands [--json]                       # read: agent-facing inventory
```

Global-ish flags available on most subcommands: `--root DIR` (themes
directory; default `themes/` relative to the working directory),
`--state-root DIR` (override the state root; testing), `--json`.

## Safety convention

* **Read-only** commands: `theme list|current|validate|preview`,
  `status`, `doctor`, `version`, `wallpaper list|current`, `commands`.
* **Write** commands: `theme apply`, `theme create`, `theme rollback`,
  `wallpaper set`.
  Each requires confirmation on a TTY, or `--yes` when non-interactive
  (pipes, scripts, agents). Without `--yes` on a non-TTY stdin they
  refuse with exit code `2`.
* `theme validate --strict` treats warnings as validation errors.
* `theme apply --force` overwrites user-modified managed targets;
  every forced overwrite is reported as a warning.
* `theme apply --dry-run` executes the read-only prefix of the pipeline
  in a sandbox and reports the exact plan (equivalent to `theme preview`).

## Machine-readable mode

Structured commands accept `--json` and then write **one JSON document
to stdout** — no progress text, no interleaved warnings. Human
diagnostics go to stderr. Every JSON document carries
`schema_version: 1` and a `command` field naming the surface.

```bash
omni theme preview default --json | jq .
omni doctor --json | jq .
omni status --json | jq .
```

## Agent ergonomics: `omni commands`

`omni commands` is the discovery surface for coding agents and
automation. It reports every leaf command with machine-readable safety
metadata derived from the live parser, so an agent can decide what is
safe to run without parsing `--help` prose:

```bash
omni commands --json | jq .
```

```json
{
  "schema_version": 1,
  "command": "commands",
  "commands": [
    {
      "name": "theme.apply",
      "mutates": true,
      "supports_yes": true,
      "supports_json": true,
      "supports_dry_run": true
    },
    {
      "name": "theme.preview",
      "mutates": false,
      "supports_yes": false,
      "supports_json": true,
      "supports_dry_run": false
    }
  ]
}
```

Contract (stable; consumed by the Session 17 OpenCode integration):

* `name` — `group.command`, or the bare group name for top-level
  commands (`status`, `doctor`, `version`, `commands`).
* `mutates` — the command writes to the system. Only `theme.apply`,
  `theme.rollback` and `wallpaper.set` are `true`.
* `supports_yes` / `supports_json` / `supports_dry_run` — derived from
  the actual argument parser, never hand-maintained.
* Every mutating command accepts `--yes` (skip confirmation for
  automation); read-only commands never do.
* Every JSON document, on success or failure, carries
  `schema_version: 1` and a `command` field naming the surface.

## Exit codes

| Code | Name                | Meaning                                   |
|------|---------------------|-------------------------------------------|
| 0    | `SUCCESS`           | command succeeded                         |
| 2    | `USAGE`             | bad arguments / cancelled confirmation    |
| 10   | `VALIDATION_ERROR`  | a theme failed validation (or `--strict`) |
| 11   | `CONFLICT`          | runtime state is inconsistent             |
| 12   | `UNSUPPORTED`       | requested capability unavailable          |
| 13   | `ACTIVATION_FAILURE`| apply/preview could not complete          |
| 14   | `ROLLBACK_FAILURE`  | rollback could not complete               |
| 20   | `INTERNAL_ERROR`    | unexpected engine failure                 |

Notes:

* `theme preview` on an unresolvable or invalid theme exits
  `ACTIVATION_FAILURE`; on an unresolvable *reference* it exits
  `INTERNAL_ERROR` (matching `theme validate`).
* `theme validate` returns `VALIDATION_ERROR` for invalid themes,
  `INTERNAL_ERROR` for a reference that cannot be found.
* `status` returns `CONFLICT` when pointers and `state.json` disagree,
  `SUCCESS` otherwise (including "no state yet").

## Schemas

### `status` (`status`)

```json
{
  "schema_version": 1,
  "command": "status",
  "state_exists": true,
  "current_theme": "tokyo",
  "previous_theme": "default",
  "current_generation": "gen-20260825T000000-1234-0",
  "previous_generation": "gen-20260824T000000-1234-1",
  "activated_at": "2026-08-25T00:00:00+00:00",
  "managed_targets": 5,
  "consistent": true,
  "details": [],
  "adapters": {"kde": {"supported": true, "applied": true, "verified": true}}
}
```

### `doctor`

Covers OS, desktop, Plasma version, session type, Python, native
binaries, XDG roots, theme/state directories, write permissions,
current/previous state, symlink integrity, managed-target conflicts and
per-adapter capability signals:

```bash
omni doctor --json | jq '.missing_binaries, .adapter_capabilities, .state_consistent'
```

`doctor` is strictly read-only and always exits `SUCCESS`.

### `theme preview`

```json
{
  "schema_version": 1,
  "command": "theme.preview",
  "ok": true,
  "status": "DRY_RUN",
  "theme": {"id": "tokyo", "name": "Tokyo Night", "mode": "dark"},
  "palette": {"background": "#14161c", "...": "..."},
  "surfaces": {"popups": {"border-width": 2}},
  "gradients": [{"group": "controls", "key": "focus-border", "value": "rgba(...) 45deg"}],
  "wallpaper": "/themes/tokyo/wallpapers/tokyo.png",
  "validation": [],
  "adapters": [{"id": "kde", "supported": false, "reason": "..."}],
  "targets": [{"target": "~/.config/...", "name": "...", "adapter": "kde"}],
  "conflicts": [],
  "warnings": [],
  "errors": []
}
```

Preview resolves, merges, validates, renders and plans targets and
adapter capabilities — but never writes live targets, mutates
current/previous state or dispatches mutation events.

### `theme current` / `version` (`no envelope`)

```json
{"current_theme": "default"}
```

```json
{"schema_version": 1, "command": "version", "package": "0.1.0", "state_schema": 1}
```

`theme current` exits `ACTIVATION_FAILURE` when no theme is active.

### `wallpaper list` / `wallpaper current` / `wallpaper set`

```json
{"active": ["file:///…png"], "wallpapers": [{"path": "…", "origin": "theme", "theme": "default", "active": true}]}
```

`wallpaper set` caches the image (content-hash) into the engine's
wallpaper cache, applies it via `plasma-apply-wallpaperimage`, journals
the pre-Omni wallpaper for rollback, and verifies by read-back.

## Examples for agents

```bash
omni theme list --json                     # discover themes
omni theme validate tokyo --json           # gate before applying
omni theme preview tokyo --json            # see exactly what would change
omni theme apply tokyo --yes --json        # activate, machine-readably
omni theme rollback --yes --json           # revert
omni status --json                         # current runtime snapshot
omni doctor --json                         # environment diagnostic
omni version --json                        # package + schema version
```