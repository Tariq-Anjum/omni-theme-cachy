# OpenCode Integration

This repository ships an [OpenCode](https://opencode.ai) integration so
coding agents can drive Omni through deterministic project commands.
The Omni CLI is the source of truth; the OpenCode commands wrap it and
never re-implement it.

Conventions verified against OpenCode `1.18.23`:

* project Markdown commands live in `.opencode/commands/`
  (not the deprecated `.opencode/command/`);
* permissions are declared in `opencode.json`
  (schema: <https://opencode.ai/config.json>);
* no custom tools are defined in `.opencode/tools/` — the CLI surface
  is sufficient, and adding a tool for every CLI command would be
  redundant.

## Permission policy (`opencode.json`)

| Category | Policy |
|----------|--------|
| read-only discovery (`read`, `glob`, `grep`, `list`) | allow |
| read-only omni commands (below) | allow — no prompting |
| local tests/builds (`pytest`, `compileall`, audit scripts, `git status/diff/log`) | allow |
| everything else in bash (`*`) | ask |
| desktop mutation (`omni theme apply/rollback`, `omni wallpaper set`) | ask |
| `git push` / `git tag` | ask |
| package installs (`pip install`, `npm install`), `sudo`, `curl`, `wget` | deny |
| file edits (`edit`) | ask |
| network reads (`webfetch`, `websearch`) | allow |

Read-only omni commands that run without prompting mirror the
`mutates: false` entries of `omni commands --json`: `theme list`,
`theme current`, `theme validate`, `theme preview`,
`wallpaper list`, `wallpaper current`, `status`, `doctor`, `version`,
`commands`. Mutating commands (`theme apply`, `theme rollback`,
`wallpaper set`) are never pre-allowed.

## Mapping: `omni commands --json` → OpenCode commands

`omni commands --json` (schema_version 1) is the machine-readable CLI
inventory (`{name, mutates, supports_yes, supports_json,
supports_dry_run}`, derived from the live argparse parser — see
[CLI.md](CLI.md)). The OpenCode command files in `.opencode/commands/`
wrap those surfaces:

| OpenCode command | omni surfaces used | mutates? |
|------------------|--------------------|----------|
| `/omni-check` | — (repo gates: audits, `pytest`, `compileall`, `git diff --check`) | no |
| `/omni-preview` | `theme preview --json` | no |
| `/omni-apply` | `theme apply --dry-run --json`, then `theme apply --yes --json` | only after a clean dry-run |
| `/omni-security` | — (security audits + `pytest tests/security` + subprocess scan) | no |
| `/omni-release-check` | `commands --json`, `doctor --json`, `theme list`, `theme validate default`, `theme preview default --json` + repo gates | no |

Rules encoded in every command body:

* the Omni CLI is the source of truth;
* nothing mutates the desktop without a dry-run and explicit `--yes`;
* nothing is pushed to GitHub automatically.

Development checkouts may not have the `omni` shim on PATH; the commands
fall back to `.venv/bin/omni`.
