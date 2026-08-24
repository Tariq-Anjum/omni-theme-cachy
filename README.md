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

**Session 05 — KDE Plasma 6 adapter: Color Scheme + wallpaper, verified live.**

- `adapters/kde/`: capability → plan → render → apply → verify →
  rollback adapter driven by the core registry/event lifecycle
- Color Scheme generation (`templates/kde/OmniTheme.colors.tpl`,
  theme-tier override in the default theme) with an explicit, tested
  palette→KDE mapping table; applied via `plasma-apply-colorscheme`;
  verified through `kdeglobals` read-back
- Wallpaper pipeline: validate → content-hash cache → native apply →
  active-wallpaper read-back (qdbus6 scripting, appletsrc fallback);
  per-theme journal for exact rollback restore
- CLI: `omni theme validate|preview|apply|current|rollback`,
  `omni status`, `omni wallpaper list|current|set`
- Design + verified-command matrix:
  `docs/architecture/KDE_ADAPTER.md`

Earlier sessions:

- Session 04 — activation state, atomic promotion, rollback, adapter
  contract (`core/activation.py`, `core/state.py`, `core/adapters.py`)
- Session 03 — template rendering, user overlays, safe staging
  (`core/renderer.py`, `core/staging.py`)
- Session 02 — semantic theme model, color engine, gradients, surface
  roles (`core/theme_model.py`, `core/color.py`)
- Session 01 — research groundwork under `docs/research/`

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
