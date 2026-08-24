# Omarchy Theming — Research Notes (Session 01)

Sources: `basecamp/omarchy` repo (`docs/theming.md`, `bin/omarchy-theme-set`,
`bin/omarchy-theme-set-templates`, DeepWiki architecture pages). Fetched
August 2026 from the `quattro`/`dev` branches.

## Core ideas worth keeping

Omarchy is a Hyprland/Wayland tiling setup, but its **theming engine design**
transports well to a traditional floating-window KDE desktop:

1. **One semantic palette file per theme** — `colors.toml`.
2. **Templates** render app configs from that palette.
3. **Staging directory** → atomic promotion to "current".
4. **User overlay** wins over system themes; user templates win over built-ins.
5. **Hooks** fire after activation so live reload stays decoupled.

## Theme directories

| Path | Role |
|------|------|
| `/usr/share/omarchy/themes/<name>/` | first-party themes (trusted) |
| `~/.config/omarchy/themes/<name>/` | user themes / git-cloned themes |
| `~/.local/state/omarchy/current/theme` | active theme dir |
| `~/.local/state/omarchy/current/next-theme` | staging dir |
| `~/.local/state/omarchy/current/theme.name` | current theme identifier |
| `~/.config/omarchy/themed/*.tpl` | user templates |

## colors.toml

Semantic-first grouping, then backgrounds, foregrounds, then the ANSI ramp:

```toml
mode = "dark"          # or a legacy empty `light.mode` marker file

accent = "#7aa2f7"
selection = "#292e42"
muted = "#414868"

background = "#1a1b26"
dark_background = "#13141c"
darker_background = "#0e0e14"
lighter_background = "#24283b"

foreground = "#a9b1d6"
dark_foreground = "#565f89"
light_foreground = "#b4bee6"
bright_foreground = "#c0caf5"

red = "#f7768e"
blue = "#7aa2f7"
# … color0–color15
```

- Legacy short names (`bg`, `fg`, `dark_bg`, …) still resolve; canonical names
  take precedence and are also re-exposed under legacy names.
- Neutral ramp is centered on `background → bright_foreground`; dark themes
  read darkest→lightest, light themes lightest→darkest.
- Shell palette foundation: `foreground`, `background`, `accent` (fallback
  `color4`), `muted` (= ANSI 8), urgent comes from `red`/`color1`.

## Template placeholders

| Placeholder | Output for `accent = "#7aa2f7"` |
|-------------|--------------------------------|
| `{{ accent }}` | `#7aa2f7` |
| `{{ accent_strip }}` | `7aa2f7` |
| `{{ accent_rgb }}` | `122,162,247` |

Plus color-mixing helpers (`mix background foreground 15%`) and gradient
helpers (`hypr_gradient`, `shell_gradient`, `gradient_start` with fallbacks).
Implementation upstream is literally a generated `sed` script over
`key=value` pairs — simple, fast, no template-engine dependency.

## Staging + activation flow (`omarchy-theme-set <name>`)

1. Build clean staging at `…/current/next-theme`.
2. Copy first-party theme from `themes/<name>/`.
3. Overlay user theme `~/.config/omarchy/themes/<name>/` (full when
   hand-written; filtered when it came from a git clone — `.git` marks it).
4. Optionally synthesize `colors.toml` from an old-style `alacritty.toml`.
5. Render templates into staging (**only if** `colors.toml` exists;
   **never** overwrite files already staged by hand — hand-written wins).
6. User templates processed before built-ins; same output filename ⇒ built-in
   skipped.
7. Atomically move staging → `current/theme`, write `theme.name`,
   notify the running shell.
8. Fire `theme-set` hooks (`~/.config/omarchy/hooks/theme-set*`, theme name in
   `$1`) and run parallel per-app retint commands.
9. Whole operation serializes on a `flock`.

## Security model for third-party themes

A `.git` directory ⇒ cloned from a stranger ⇒ denylist filtering at staging:

- drop any `*.lua` (Hyprland `require`s them; Neovim loads them),
- drop terminal configs that name the launched program
  (`alacritty.toml`, `foot.ini`, `ghostty.conf`, `kitty.conf`),
- drop `vscode.json` (installs arbitrary JS extension),
- drop all symlinks at any depth,
- keep everything that is *colour* (a cloned theme may still fully define
  `btop.theme`, `shell.toml`, etc.),
- dropped files are named on stderr and regenerated from templates instead.

The filter lives in staging (not install time) so it also covers themes
installed before the rule existed and later `git pull` updates. Upstream is
explicit: this is a provenance statement, not a sandbox — archives extracted
by hand are indistinguishable from user-written themes.

Tests enforce that every new template must be classified code-vs-colour
(`test/shell.d/theme-staging-test.sh`).

## Tests

Upstream keeps focused suites: `./test/cli`, `./test/shell` — including a test
that fails when a new `*.tpl` appears without a security classification.
Lesson: make the security policy test-enforced, not convention-enforced.

## What we deliberately do NOT port

- Hyprland/Foot/Walker/Waybar specifics (KDE equivalents differ fundamentally).
- The `sed`-script renderer — Python gives us real parsing with `tomllib`
  while staying dependency-free.
- `light.mode` marker-file legacy — we use `mode = "light"` in TOML only.
