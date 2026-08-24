# Omarchy Architecture — Crucial Inputs (Session 02)

Deep-dive companion to [`OMARCHY_THEMING.md`](OMARCHY_THEMING.md). Every claim
below was verified against the actual source of `basecamp/omarchy` (branch
`quattro`, ~6,100 commits) cloned and read directly in August 2026 — not
summarized from secondary sources. File references like
`bin/omarchy-theme-set` point into that repo (installed under
`/usr/share/omarchy/`).

The four mechanisms documented here are the ones omni-theme-cachy must
reproduce for KDE Plasma 6:

1. User overlays (theme-level)
2. User templates (template-level)
3. Surface roles (`shell.toml`) separated from the base palette
4. Staged activation + symlinks for zero-downtime switching

---

## 1. User Overlays: `~/.config/omarchy/themes/<name>/`

### Two theme roots, one namespace

| Root | Path | Trust |
|------|------|-------|
| System | `$OMARCHY_PATH/themes/<name>/` → `/usr/share/omarchy/themes/` | Shipped by the distro, fully trusted |
| User | `~/.config/omarchy/themes/<name>/` | Trusted only if hand-written; filtered if git-cloned |

Discovery treats them as a **union, not a preference list**:

- `bin/omarchy-theme-list`: `find` on both roots, merged + `sort -u`. A user
  theme with the same name as a system theme does not shadow it in the list —
  it *extends* it at staging time.
- `bin/omarchy-theme-dir`: prefers the user dir when it exists; used by tools
  that want "the" source of a theme (e.g. preview rendering).

### Overlay happens at staging, file-granular

`bin/omarchy-theme-set` never mutates either root. It builds the overlay into
the staging directory:

```bash
rm -rf "$NEXT_THEME_PATH"                       # clean slate every run
mkdir -p "$NEXT_THEME_PATH"
cp -r "$OMARCHY_THEMES_PATH/$THEME_NAME/"* "$NEXT_THEME_PATH/"   # base first
cp -r "$USER_THEMES_PATH/$THEME_NAME/"*   "$NEXT_THEME_PATH/"   # user wins
```

Properties worth copying:

- **Whole-file granularity.** There is no key-level merge inside config files.
  A user `shell.toml` replaces the system `shell.toml` outright. Simplicity is
  deliberate: the template layer (§2) covers the "tweak one value" case.
- **Missing user dir is a no-op** (`cp -r ... 2>/dev/null`), so pure-system
  themes need no special-casing.
- **Additive files work**: anything the user drops in that doesn't collide
  (e.g. an extra `backgrounds/` image) simply joins the staged tree.
- The same pattern applies to backgrounds specifically:
  `choose_theme_background()` searches **both**
  `~/.config/omarchy/backgrounds/$THEME_NAME/` *and*
  `current/theme/backgrounds/`, merges them into one sorted pool, and rotates
  through it. Users extend a theme's wallpaper set without touching the theme.

### The provenance fork (security-relevant)

Before overlaying, `theme_came_from_a_repo()` decides how the user dir is
staged — the exact test `bin/omarchy-theme-extras` uses elsewhere:

```bash
[[ ! -L $source && -d $source/.git ]]    # real dir containing .git ⇒ cloned
```

- **Hand-written or symlinked working copy** → plain `cp -r` overlay (above).
  "It is their machine and their file."
- **Git clone** (`omarchy theme install <url>`) → `stage_installed_theme()`:
  - Drop **all `*.lua`** (Hyprland `require`s `hyprland.lua`/`gum_env.lua` at
    login; Neovim loads `neovim.lua` at startup).
  - Drop `INSTALLED_THEME_DENIED=(alacritty.toml foot.ini ghostty.conf kitty.conf vscode.json)`
    — each names a program to launch / extension to install.
  - Drop **every symlink at any depth** (`stage_installed_dir` copies without
    ever following links — an `unlock.png` symlink could exfiltrate any
    readable file).
  - Keep everything that is *colour*: a cloned theme may still ship complete
    `btop.theme`, `chromium.theme`, `helix.toml`, `shell.toml`,
    `icons.theme`, …
  - Dropped files are named on stderr; templates regenerate them instead.
  - Legacy themes with only `alacritty.toml`: palette extracted via
    `omarchy-theme-colors-from-alacritty` **in a scratch dir**, so the derived
    `colors.toml` is staged but the terminal config itself never is.

Filtering lives at **staging**, not at install time, so it also covers themes
cloned before the rule existed and files gained later via `git pull`
(`bin/omarchy-theme-update`). Upstream is explicit that this is a provenance
statement, not a sandbox.

### Takeaways for omni-theme-cachy

- Overlay = copy base → overwrite with user files, into staging; never edit
  either source.
- Union-based listing; user-dir-preferring resolution.
- A provenance check (we can use a manifest/signature instead of `.git`)
  gating which files a third-party theme may contribute, enforced in staging,
  with dropped files reported.
- Per-user background pools layered over theme wallpapers.

---

## 2. User Templates: `~/.config/omarchy/themed/*.tpl`

### Precedence chain

`bin/omarchy-theme-set-templates` builds its input list user-first:

```bash
template_files=("$USER_TEMPLATES_DIR"/*.tpl "$TEMPLATES_DIR"/*.tpl)
```

then renders each to `next-theme/<basename-without-.tpl>` under one guard:

```bash
if [[ ! -f $output_path ]]; then sed -f "$sed_script" "$tpl" >"$output_path"; fi
```

This yields a **two-layer precedence** with no extra code:

1. **Hand-written beats generated.** A file already staged from the theme dir
   (e.g. a theme author's bespoke `shell.toml` or `hyprland.lua`) exists, so
   *no* template can overwrite it.
2. **User template beats built-in template.** Same basename ⇒ user's version
   renders first, built-in output skipped. This is how a local customization
   (e.g. always add a font fallback line to every terminal config) applies
   **across all themes** without touching upstream files.

### Rendering engine

No template library — a generated `sed` script over resolved palette pairs:

- For every resolved key `K`: `{{ K }}`, `{{ K_strip }}` (no `#`),
  `{{ K_rgb }}` (decimal triple) substitutions are emitted.
- Templates are pre-scanned (grep) for function tokens so those get values
  too:
  - `{{ mix A B 15% }}` (+ `_strip`/`_rgb`) — hex blending, fraction or %.
  - `{{ hypr_gradient KEY FALLBACK }}` — Lua literal: string when solid,
    `{ colors = {…}, angle = N }` table when gradient.
  - `{{ shell_gradient KEY FALLBACK }}` — space-joined stops + `Ndeg`.
  - `{{ gradient_start KEY FALLBACK }}` — first stop as flat color.
  - Fallback = another palette key name or a literal.

### Palette resolution feeding the renderer

All values come from the shared parser `bin/omarchy-theme-color --all`, so
templates, OSC sequences, tmux, GNOME and previews resolve **identically**:

- Legacy short names (`bg`, `fg`, `dark_bg`…) ↔ canonical names, canonical
  wins, both exposed afterwards.
- ANSI `color0–15` ↔ semantic names (`red`=color1, `muted`=color8, …).
- Derived shades synthesized when absent (`dark_background` = bg mixed 25%
  black; brights mixed 20% white; `brown` from orange, etc.) — a theme needs
  surprisingly few keys to be complete.
- Mode precedence: `mode` key → legacy `theme_type` → sibling `light.mode`
  file → background-luminance auto-detect (>382 sum-of-RGB = light) → dark.
- **Value charset validation** on parse: keys/values outside a safe charset
  are rejected *with a message*, because values become `sed` replacement text
  (a stray `|`, `\` or `&` would corrupt every rendered file silently).

Templates render **only if the staged theme has `colors.toml`** — no palette,
no generated files.

### Takeaways for omni-theme-cachy

- User-template dir with first-position iteration + never-overwrite guard =
  cheap, correct two-layer override. Adopt verbatim conceptually.
- Keep the placeholder grammar small (`key`, `key_strip`, `key_rgb`, `mix`,
  gradients) — it is fully expressible in Python without a dependency.
- Central resolver shared by *every* consumer; validate/announce bad values
  rather than passing them through.

---

## 3. Surface Roles: `shell.toml`

The core separation: **`colors.toml` = what the palette is;
`shell.toml` = how UI surfaces use it.**

### Generation & three override paths

Default `shell.toml` is rendered per theme from
`default/themed/shell.toml.tpl` (placeholders pull from `colors.toml`). A
theme/user can then intervene via the §1/§2 mechanisms, plus a third,
section-scoped one:

- Ship a full `themes/<name>/shell.toml` → replaces generated file entirely
  (never-overwrite guard).
- Ship `shell.<section>.toml` (e.g. `shell.lock.toml`) →
  `apply_shell_section_overrides()` splices just that `[section]` into the
  generated file after template rendering. The section header inside the
  override file is optional — **the filename picks the target section**
  (`strip_shell_section_header` + awk splice). Tokyo Night uses exactly this:
  a five-line `shell.lock.toml` overriding only lock-screen colors.

### Section inventory (from `default/themed/shell.toml.tpl`)

| Section | Role |
|---------|------|
| `[bar]` | Bar background/text + `active` for attention modules; cross-axis sizing |
| `[hyprland]` | **Shared border tokens** (`active-border`, `active-border-foreground`) other sections reference symbolically |
| `[controls]` | Interactive-control chrome state machine (below) |
| `[spacing]` | `scale`, `scale-with-font`, named tokens xxs…huge, control/popup metrics |
| `[font]` | `base-size` rem root; per-token px overrides caption…display-large |
| `[popups]` | Shared bar-flyout surface (dropdowns, OSD, popup cards) |
| `[tooltip]` | Hover tooltips (alpha 0.97 legacy mirror) |
| `[notifications]` | Toast surface + countdown accent |
| `[launcher]` / `[menu]` | Card + scrim + selected-row tokens (clipboard/emoji inherit menu) |
| `[polkit]` | Auth prompt incl. error state tinting |
| `[lock]` | Lock input field with idle/active/error border states |
| `[image-picker]` | Cardless carousel: scrim wash + selected/unselected slice borders |

### Key design conventions

- **Alpha companions.** Any color token may have `<token>-alpha` ∈ [0,1]
  (`background-alpha`, `scrim-alpha`, `border-alpha`, …). Consumers compose
  `color × alpha`; alphas clamp.
- **Solid-or-gradient in one key.** Borders accept `"#7aa2f7"` or
  Hyprland-style `"rgba(33ccffee) rgba(00ff99ee) 45deg"` in the *same* key —
  explicitly no separate `-gradient` keys. Alpha companions apply to solids
  and to every gradient stop (multiplicative with stop alpha).
- **Symbolic role references.** Sections reference shared tokens by name:
  `border = "hyprland.active-border"`. The QML consumer resolves these
  recursively against the flat dict before falling back to foundational
  palette roles (`foreground`, `accent`, `urgent`, `muted`, `background`,
  `transparent`).
- **CSS-style width lists.** `border-width` = `N` / `"T B"` / `"T R B L"` /
  `"T R B L"`; per-side keys (`border-width-left`) override the list;
  state-token prefixes for stateful surfaces (`border-active-width-left`).
- **Control states** (`[controls]`): `normal`, `hover-cursor`, `focus`,
  `selected`, plus momentary `pressed-fill-alpha` / `selection-fill-alpha`;
  each has `color`, `fill-alpha`, `border`, `border-width`,
  `border-alpha`. Defaults deliberately make hover/focus identical; themes
  differentiate by overriding four lines.
- **Scale system.** `[spacing] scale` multiplies shared dimensions;
  `scale-with-font` ties spacing/bar sizes to `[font] base-size`; individual
  tokens can be pinned in px without breaking the rest.

### Runtime consumption — three merge layers

QML side (`shell/Commons/Color.qml` + `Style.qml`), verified behavior:

1. `parseShell()` walks the TOML-ish file into a **flat dict**
   `"section.key" → raw string` (quoted strings, bare numbers, width lists,
   bare role names; inline comments tolerated). Numbers stay strings; readers
   coerce.
2. Layers kept separate and merged with **user keys winning**:
   - `themeShellValues` ← `~/.local/state/omarchy/current/theme/shell.toml`
     (replaced wholesale on every switch),
   - `userShellValues` ← `~/.config/omarchy/shell.toml` (**machine-level,
     survives switches**; watched live — this is where
     `omarchy display text size` writes `[font] base-size` and it takes
     effect without restart).
3. Every `pick(key, fallback)` bottoms out in the **foundational palette**
   loaded from `colors.toml` (`foreground/background/accent/muted/urgent`
   where urgent ← `red`/color1). Missing sections degrade gracefully — a
   theme that ships only `colors.toml` still yields a coherent UI.

### Hot reload path

Theme switches do **not** rely on file watching for theme files
(`watchChanges: false`): `omarchy-theme-set` base64-encodes the new
`colors.toml` + `shell.toml` and pushes them over Quickshell IPC
(`omarchy-shell shell applyTheme <colors_b64> <shell_b64>`); the shell
re-parses and reassigns the whole dict so QML bindings re-evaluate atomically.
Only the machine-level user file is watched.

### Takeaways for omni-theme-cachy

For KDE we translate surfaces to Kirigami/QQC2 roles, but keep the shape:

- Palette file ≠ surface file; surface file references palette via
  placeholders at generation time and via symbolic role refs at runtime.
- Section-scoped overrides keyed by filename (`shell.<section>.toml` analog)
  are cheap to implement and very theme-author-friendly.
- Alpha companions + solid-or-gradient single-key borders + CSS width lists
  form a compact border language worth mirroring in our Plasma adapter
  (mapping onto plasma decorations/aurorae where possible).
- Machine-level user `shell.toml` layered above theme values, hot-watched —
  direct precedent for our planned `~/.config/omni/shell-overrides.toml`.

---

## 4. Staging & Symlinks: zero-downtime switching

### State layout

```
~/.local/state/omarchy/current/
├── next-theme/     # staging area (exists only mid-switch)
├── theme/          # active theme (fully materialized, templates rendered)
├── theme.name      # active theme identifier ("tokyo-night")
└── background      # symlink → active wallpaper image
```

`docs/file-layout.md` draws the line explicitly: `~/.local/state/` =
generated runtime state; `~/.config/omarchy/` = only what a user would
version in a dotfile manager (user themes, hooks, templates, plugins).

### Switch sequence (`bin/omarchy-theme-set`)

Serialization first — a **`flock`** on
`${XDG_RUNTIME_DIR:-/tmp}/omarchy-theme-set-lock`, because concurrent switches
would otherwise race the shared staging dir and symlinks:

1. Validate theme exists in either root; reject `.`/`..`/path-traversal names
   early (name normalized: lowercase, spaces→dashes, `<>` stripped).
2. Wipe + recreate `next-theme`.
3. Stage: system theme copy → user overlay (full or filtered, §1) →
   synthesize `colors.toml` from legacy `alacritty.toml` if needed →
   render templates (§2) → splice `shell.<section>.toml` overrides.
4. Snapshot current wallpaper (**hardlink**, falling back to cp) into
   `~/.cache/omarchy/background-transitions/previous-<pid>.<ext>` for the
   cross-fade; pick next wallpaper from the merged pool (§1).
5. **Promote:** `rm -rf current/theme && mv next-theme current/theme` — a
   rename within the same filesystem. Write `theme.name`.
6. Push payloads to the running shell over IPC: `shell applyTheme` (or
   `background themeTransition old-snapshot new-snapshot final colors shell`
   for the animated case), then `ln -nsf` the background symlink. Snapshots
   are garbage-collected after 3 s.
7. `flock -u 9` — **the critical section ends here, deliberately before the
   slow part.** Queued selections only wait for staging+promotion+IPC, not
   for app retints.
8. Parallel `post_theme_commands`: terminal reloads (`touch` alacritty conf,
   SIGUSR1→kitty, SIGUSR2→ghostty), hyprctl reload, btop/opencode/helix
   restarts, foot/tmux/gnome/pi/claude/browser/vscode/obsidian/keyboard-RGB
   retints → then the `theme-set` hook (`~/.config/omarchy/hooks/theme-set`
   + `.d/`, theme name in `$1`) → selector cache warmup.

### Why consumers never see torn state

- Live processes get content **pushed via IPC**; they don't re-read files
  during a switch (theme FileViews unwatched).
- Lazy readers (`omarchy-theme-color`, OSC emitter, Hyprland Lua) read
  `current/theme/...` on demand and see either the old or the new complete
  tree — the promotion rename is atomic. (Upstream accepts the sub-millisecond
  rm→mv gap between the two commands; nobody observes it because nothing is
  watching.)
- Terminals additionally get live OSC sequences (`omarchy-theme-osc` emits
  OSC 4/10/11/12/17/19) so even already-open panes retint without restart.
- Headless contexts (ISO chroot: `OMARCHY_THEME_HEADLESS=1`) skip IPC but
  still stage, promote, and create the `background` symlink so first login
  renders correctly.

### Symlink roles summarized

| Link | Purpose | Update style |
|------|---------|--------------|
| `state/current/theme` | Materialized active theme | Atomic `mv` of staged dir |
| `state/current/background` | Active wallpaper (may live anywhere, incl. user dirs outside the theme) | `ln -nsf` swap + IPC push |
| `state/current/theme.backgrounds` pool | rotation pool across theme + user dirs | recomputed per switch |

Hyprland integration rides on the same layout: `default/hypr/bootstrap.lua`
puts `~/.local/state/?.lua` **first** on Lua `package.path`, so the staged
theme directory doubles as module namespace `omarchy.current.theme.*` —
`require_optional.module("omarchy.current.theme.hyprland")` transparently
loads (or skips) the theme's generated/staged `hyprland.lua`.

### Takeaways for omni-theme-cachy

- `next-*` staging + single atomic promotion into `current` maps directly
  onto our planned Plasma staging (plasma theme, color scheme, icons, GTK).
- flock-equivalent (lockfile via `fcntl.flock`) around the whole
  build-promote critical section; release before slow adapter apply steps.
- Push-notify live sessions over IPC/DBus where possible (Plasma: `plasma-apply-*`
  + KConfig change signals), keep file reads as lazy fallback.
- Wallpaper as a symlink slot independent of theme content enables per-user
  pools + transition snapshots; Plasma equivalent should follow suit.
- Hooks after promotion (`hooks/theme-set.d/`) keep adapters decoupled from
  the core switcher.

---

## Source index (verified reading)

| Mechanism | Upstream files |
|-----------|----------------|
| Overlays, staging, promotion, locking, security filter | `bin/omarchy-theme-set`, `test/shell.d/theme-staging-test.sh` |
| Template rendering, precedence, section splices | `bin/omarchy-theme-set-templates`, `default/themed/*.tpl` |
| Palette resolver / aliases / derivation / mode | `bin/omarchy-theme-color`, `bin/omarchy-theme-colors-from-alacritty` |
| Surface-role consumer, 3-layer merge, IPC reload | `shell/Commons/Color.qml`, `shell/Commons/Style.qml` |
| Theme lifecycle UX (list/install/update/remove/extras/dir/refresh/switcher) | `bin/omarchy-theme-{list,install,update,remove,extras,dir,refresh,switcher}` |
| Background symlinks & transitions | `bin/omarchy-theme-bg-{set,current,cache,next,switcher}`, snapshot logic in `omarchy-theme-set` |
| Hyprland pickup of staged theme as Lua modules | `default/hypr/bootstrap.lua`, `default/hypr/{omarchy,envs}.lua`, `default/hypr/require_optional.lua` |
| Upstream's own write-ups | `docs/theming.md`, `docs/file-layout.md` |
