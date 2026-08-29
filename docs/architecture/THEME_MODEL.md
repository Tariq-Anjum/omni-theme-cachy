# Theme Model — `themes/<name>/`

A theme is a directory of declarative TOML plus optional artwork. Everything
is value data; loading is strict (bad syntax fails with file, key and value
named), while *rules* (missing roles, low contrast) are reported as
validation issues by `core/validation.py`. Implementation:
`core/theme_model.py`, `core/theme_loader.py`.

## Layout

```
themes/<name>/
├── theme.toml      # [theme] metadata + optional [wallpaper]
├── colors.toml     # semantic roles → '#RRGGBB' (+ the ANSI ramp)
├── surfaces.toml   # how UI surfaces use the palette ([popups], [controls])
├── wallpapers/     # artwork (default theme ships generated PNG)
└── templates/      # optional theme-tier template overrides
```

Single-file themes are supported: `colors`/`surfaces` may live as tables
inside `theme.toml`; a top-level `colors.toml`/`surfaces.toml` wins when
both exist.

## `theme.toml`

```toml
[theme]
name = "Default"     # display name
id   = "default"     # canonical id (lowercase, used by state/overlays)
version = 1          # positive integer
mode = "dark"        # "dark" | "light" (mirrors Plasma scheme polarity)

[wallpaper]
default = "wallpapers/default.png"   # relative to the theme dir
```

All four `[theme]` keys are required. Unknown sections are reported as
warnings by `omni theme validate`.

## `colors.toml`

Flat table of role → normalized `#RRGGBB` (or `#RGB`, normalized on load —
but validation *errors* on un-normalized storage, so author `#RRGGBB`).

Required roles (44 total, `SEMANTIC_ROLES + ANSI_ROLES` in
`core/theme_model.py`):

| Group | Roles |
|---|---|
| Interaction | `accent`, `accent_secondary`, `selection`, `muted` |
| Surfaces | `background`, `dark_background`, `darker_background`, `lighter_background` |
| Text | `foreground`, `bright_foreground`, `light_foreground`, `dark_foreground` |
| Status | `success`, `warning`, `error`, `info` |
| Base hues | `red` `green` `yellow` `blue` `magenta` `cyan` |
| Bright hues | `bright_red` `bright_green` `bright_yellow` `bright_blue` `bright_magenta` `bright_cyan` |
| ANSI ramp | `color0` … `color15` (plain data; adapters map them per-app) |

Unknown extra roles are allowed (warning) so themes can carry app-specific
data.

## `surfaces.toml` — the Omarchy `shell.toml` analog

`colors.toml` says what the palette is; `surfaces.toml` says how UI surfaces
use it. Layout is `group → key → value`. Known groups today:
`popups`, `controls` (unknown groups are allowed with a warning).

Value language (`core/color.py:classify_surface_value`):

| Key shape | Value form | Example |
|---|---|---|
| `*width` | int or 1–4-int CSS-style list `T R B L` | `border-width = 2` / `"2 4"` |
| `*alpha` | number in `[0, 1]` | `background-alpha = 0.9` |
| color | `#RRGGBB` | `border = "#4f9eea"` |
| gradient | 2+ stops `rgba(RRGGBBAA) rgba(RRGGBBAA) [Ndeg]` | `focus-border = "rgba(4f9eeaee) rgba(8f6cafee) 45deg"` |
| dimension | bare non-negative int | `padding = 8` |

Booleans, floats, negative numbers and malformed values are load errors.
A theme without `surfaces.toml` is usable (adapters fall back to
palette-derived defaults) but warned about.

## Wallpaper

`[wallpaper] default` resolves relative to the theme directory. Validation
errors when the file is missing and warns when it lives outside the theme
(it will not travel with the theme). Supported image formats are sniffed by
magic bytes: png/jpeg/gif/bmp/webp.

## Resolution of a theme reference

`find_theme()` (used by `theme validate/preview/apply`): an explicit path
wins; otherwise the themes root is searched by directory name, then
`theme.id`, then `theme.name`. Use `--root` to point at another collection.

## User overlays

A user directory `~/.config/omni-theme/themes/<id>/` (or the theme's
directory name) containing only the files being tweaked (`colors.toml`,
`surfaces.toml`) is deep-merged over the base: color roles replace or add
roles; surface entries replace at `(group, key)` granularity.
`[theme]` metadata and wallpaper always stay with the base — users tweak
values, never identity. See [OVERRIDES.md](../user/OVERRIDES.md).

## Validation rules (`omni theme validate`)

* **Errors** refuse activation: missing required colors, malformed or
  un-normalized colors, load failures, missing wallpaper file, malformed
  surface values.
* **Warnings** are design signals: WCAG contrast below 4.5:1 (text pairs:
  `foreground`/`bright_foreground`/`muted`/`foreground-on-selection` vs
  `background`/`selection`) or below 3.0:1 (accent/status pairs), no
  wallpaper, no surfaces, unknown roles/groups/sections. `--strict` treats
  warnings as failures.

## CLI surface

```
omni theme list [--json] [--root DIR]
omni theme current [--json] [--state-root DIR]
omni theme validate <ref> [--strict] [--json]
omni theme preview  <ref> [--json]     # read-only full plan
omni theme apply    <ref> [--yes] [--dry-run] [--force] [--json]
omni theme rollback [--yes] [--json]
```

Exit codes are documented in [CLI.md](../user/CLI.md).
