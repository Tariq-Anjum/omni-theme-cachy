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

**Session 02 — theme model, color engine, gradients, and surface roles committed.**

- Semantic theme model (`core/theme_model.py`): required metadata, 28
  semantic roles + full ANSI ramp (`color0`–`color15`)
- Surface roles (`surfaces.toml`, Omarchy `shell.toml` analog):
  `[popups]` / `[controls]` groups with solid-or-gradient border values,
  CSS-style width lists (`"2 4 6 8"`), `<key>-alpha` companions
- TOML loading with strict errors (`core/theme_loader.py`, stdlib `tomllib`)
- Color engine: `#RRGGBB` (+ documented `#RGB` normalization), mixing,
  WCAG luminance/contrast, Omarchy gradient parsing
  (`rgba(RRGGBBAA) … 45deg`), border-width shorthand (`core/color.py`)
- Validation API + `omni-theme theme validate <ref> [--json] [--strict]`
  (`core/validation.py`, `core/cli.py`) — WCAG-derived contrast warnings,
  never invented thresholds
- Neutral dark default theme in `themes/default/` including a baseline
  `surfaces.toml`; original generated wallpaper (see
  `scripts/generate_default_wallpaper.py`)

Session 01 groundwork:

- `docs/research/ENVIRONMENT.md` — verified machine/tooling inventory
- `docs/research/OMARCHY_THEMING.md` — upstream design study
- `docs/research/KDE_PLASMA_6.md` — Plasma theming internals
- `docs/research/LINUX_THEME_ENGINES.md` — pywal / Stylix / Gradience survey
- `docs/research/ARCHITECTURE_DECISIONS.md` — the decisions and why

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
