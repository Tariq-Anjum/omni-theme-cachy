# Session 02 — Theme Model, Color Engine, and Surface Roles

## Objective
Implement the semantic theme model, TOML loading, schema validation, color utilities, gradient parsing, UI surface roles, and unit tests.

## Prerequisite
Session 01 must be complete.

Inspect:
```bash
git status
git log --oneline -5
```

## 1. Theme architecture

Implement:
```text
core/theme_loader.py
core/theme_model.py
core/color.py
core/validation.py
core/errors.py
```

Use Python 3.11+ standard library wherever practical.

Use:
- `tomllib`
- `dataclasses`
- `pathlib`
- `re`
- `json`

Avoid unnecessary dependencies.

## 2. Theme structure

Use:
```text
themes/<theme>/
├── theme.toml
├── colors.toml
├── surfaces.toml
└── wallpapers/
```

`theme.toml` contains metadata:
```toml
[theme]
name = "Default"
id = "default"
version = 1
mode = "dark"

[wallpaper]
default = "wallpapers/default.jpg"
```

`colors.toml` contains semantic colors. `surfaces.toml` contains UI surface roles (new — see section 4).

## 3. Semantic palette (`colors.toml`)

Support at least:
```text
accent
accent_secondary
selection
muted
background
dark_background
darker_background
lighter_background
foreground
dark_foreground
light_foreground
bright_foreground
success
warning
error
info
red
green
yellow
blue
magenta
cyan
bright_red
bright_green
bright_yellow
bright_blue
bright_magenta
bright_cyan
color0..color15
```

Follow the semantic-first philosophy used by Omarchy, but do not copy Hyprland-specific concepts into the KDE engine.

## 4. Surface Roles (`surfaces.toml`)

Implement UI control definitions inspired by Omarchy's `shell.toml`, kept separate from base semantic colors so borders, alphas, popups, and controls can be tuned independently:

```toml
[popups]
background = "#1a1b26"
border = "#7aa2f7"
border-width = 2

[controls]
normal-border = "#a9b1d6"
focus-border = "rgba(33ccffee) rgba(00ff99ee) 45deg"
```

Surface roles are consumed by adapters (e.g. KDE tooltip/complementary colors, GTK4 `@define-color`) in later sessions — this session only defines and validates the model.

## 5. Color and gradient engine

Implement:
```text
hex_to_rgb()
rgb_to_hex()
strip_hex()
hex_to_rgb_string()
mix()
mix_rgb()
relative_luminance()
contrast_ratio()
parse_gradient()
parse_border_width()
```

`parse_gradient()` must parse Omarchy-style gradient strings, e.g. `"rgba(33ccffee) rgba(00ff99ee) 45deg"`.

`parse_border_width()` must parse CSS-style shorthand lists, e.g. `"2 4 6 8"`.

Validate:
- `#RRGGBB`
- optionally `#RGB` only if deliberately normalized and documented
- gradient syntax
- border-width syntax

Reject malformed colors, gradients, and border widths.

## 6. Color helpers

Support these conceptual template values:
```text
{{ accent }}
{{ accent_strip }}
{{ accent_rgb }}
{{ mix background foreground 15% }}
{{ mix_strip background accent 35% }}
{{ mix_rgb color0 color7 50 }}
{{ kde_gradient ... }}
```

The renderer itself is Session 03; this session only defines the helper engine/API.

## 7. Validation

Implement:
```bash
omni theme validate <theme>
```
only if CLI scaffolding is already available; otherwise expose the validation API and defer CLI wiring.

Validate:
- required metadata
- required colors
- valid color syntax
- valid gradient syntax
- valid border-width syntax
- wallpaper references
- unknown/duplicate data where appropriate
- contrast warnings for meaningful foreground/background pairs

Do not invent arbitrary failure thresholds.

## 8. Tests

Create:
```text
tests/unit/test_theme_loader.py
tests/unit/test_theme_model.py
tests/unit/test_color.py
tests/unit/test_validation.py
```

Test normal and malformed input, including gradient parsing and CSS-style border widths.

Run:
```bash
python -m pytest
```
or the project's selected test runner.

## 9. Default theme

Create a coherent neutral default theme, including a baseline `surfaces.toml`.

Do not use copyrighted artwork.

## 10. Verification

Run:
```bash
python -m compileall core adapters
python -m pytest
git diff --stat
git status
```

## 11. Commit
```bash
git add .
git commit -m "feat: implement semantic theme model, gradients, and surface roles"
```

## Exit condition
Stop after the theme model, color engine, and surface roles are tested and committed. Do not implement activation or real desktop changes.