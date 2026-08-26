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

New Project

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
