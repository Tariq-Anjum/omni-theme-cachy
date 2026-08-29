# omni-theme-cachy

A universal theming engine for **CachyOS running KDE Plasma 6**, inspired by
the Omarchy theming system but built for a traditional floating-window,
mouse-driven Plasma desktop.

One semantic color palette (`themes/<name>/colors.toml`) is rendered through
templates into per-app configuration and applied through KDE's own tooling
(`plasma-apply-colorscheme`, `plasma-apply-desktoptheme`,
`plasma-apply-wallpaperimage`, …) — with staging, atomic activation,
user overrides, rollback, and a security model for third-party themes.

## Status

**Session 16 completed** — KWin scope hygiene is verified and documented:
a mechanical scan confirms no code path in `core/`, `adapters/`, `hooks/`
or `scripts/` invokes a package manager (`pacman`/`yay`/`paru`/`dnf`/`apt`/
`zypper`/`flatpak`/`snap`), no code references KWin or tiling at all, and
no `BorderlessMaximizedWindows` (or any window-behaviour setting) exists —
so a normal `omni theme apply default --yes` cannot install packages,
enable KWin scripts, change tiling behaviour, or replace KWin. The session
13 `kwinrc` guard tests still pin the boundary, and
`docs/user/OPTIONAL_KWIN_SCRIPTS.md` now names the out-of-scope community
tiling scripts (Krohnkite, Kzones, Polonium, PlasmaZones) with
verified upstream sources, explicitly without endorsement or security
review. Findings recorded in
`docs/architecture/OWNERSHIP_AND_SECURITY.md`
(authoritative execution state: `raw/00_PROJECT_MANIFEST.json`).
Prior baseline: session 15 — installation is now a real end-user path:
`install.sh` clones (or fast-forwards) the repository into
`~/.local/share/omni-theme-cachy`, installs it into a dedicated venv,
and exposes `omni`/`omni-theme` via `~/.local/bin` shims — no `sudo`, no
system-Python mutation, idempotent, and refusing to clobber a modified
clone. A GitHub Actions smoke test (archlinux container) installs the
commit under test and runs `omni version`, `omni theme list` and
`omni commands --json`. See `docs/user/GETTING_STARTED.md` for the
install methods.
Prior baseline: session 14 — the CLI is now a predictable agent API:
every mutating command (`theme apply`, `theme rollback`,
`wallpaper set`) is gated by `--yes`, all JSON surfaces (success and
failure) carry `schema_version: 1` with diagnostics on stderr only,
and the new `omni commands [--json]` inventory reports machine-readable
safety metadata (mutates / supports_yes / supports_json /
supports_dry_run) derived from the live parser
(authoritative execution state: `raw/00_PROJECT_MANIFEST.json`).
Prior baseline: session 13 — KDE INI configuration writes are section-safe:
a central `core/kde_config.py` owns all KConfig-style parsing and editing
(verbatim keys, last-wins, no duplicate sections, `[$e]`-style key suffixes
preserved, byte-precise edits), the Konsole profile surgery and the
`konsolerc`/`kdeglobals` parsers delegate to it, `configparser` is used
nowhere, native KDE tooling (`plasma-apply-colorscheme`, `kreadconfig6`)
remains the mechanism for kdeglobals, and `kwinrc`/`plasmarc` are pinned as
never-touched by guard tests.
Prior baselines: session 12 write-path security coverage — central path
policy (`approved_roots`, `validate_write_target`, `PathPolicyError`)
verified independently across every write site, symlink-safe atomic writes
hardened against validation→replacement races (`PathPolicyError` on
mid-write symlink swaps, never followed), file copies routed through a
central atomic, policy-validated `atomic_copy`, a full write-site review
table in `docs/architecture/OWNERSHIP_AND_SECURITY.md`, an AST write-site
audit script (`scripts/audit_write_paths.py`), and symlink/TOCTOU test
coverage in `tests/security/`.
Core engine, adapters, CLI, security layer and docs are in place;
documented commands are verified against the implementation, including
live KDE Plasma 6 apply→rollback runs.

## Install

```bash
git clone https://github.com/Tariq-Anjum/omni-theme-cachy.git
cd omni-theme-cachy
bash install.sh
```

Dedicated venv, `~/.local/bin` shims for `omni` and `omni-theme`, no
`sudo`, no system-Python changes. Alternatives (one-command form,
manual/local install): [docs/user/GETTING_STARTED.md](docs/user/GETTING_STARTED.md).

## Layout

```
core/        Python interpolation/rendering engine (stdlib only)
adapters/    Per-target integrations (KDE colorscheme, plasma style, GTK, …)
themes/      TOML color palettes + wallpapers
templates/   App config templates (*.tpl with {{ placeholder }} syntax)
hooks/       Bash scripts for live reloading after activation
tests/       pytest suites
scripts/     Operational helper scripts
docs/        research/, architecture/, user/
raw/         agent execution control-plane manifests and session records
```

## Principles

1. **Generate, don't hand-edit** — artifacts go to XDG user data; application
   goes through official KDE CLI tools so running apps repaint correctly.
2. **Stage, then promote atomically** — a failed switch can never leave a
   half-applied theme.
3. **User overrides always win** — repo templates never clobber hand-written
   files or user templates.
4. **Zero runtime dependencies** — Python stdlib only (`tomllib`).
5. **Third-party themes are data, never code** — executable-content denylist,
   symlink stripping, hooks only from trusted locations.

## License

MIT — see `LICENSE`.
