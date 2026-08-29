# Divergence from Omarchy — borrowed ideas and deliberate differences

Omni Theme Cachy is a **KDE Plasma 6-native theming engine**. It uses the
Omarchy theming engine (`basecamp/omarchy`, `quattro` branch) as its primary
research corpus — it is **not an Omarchy port**.

Verification provenance: every upstream claim in this document was checked
against the live `quattro` sources in August 2026 — `docs/theming.md` and
`shell/README.md` — and against the direct source reading of
`bin/omarchy-theme-set`, `bin/omarchy-theme-set-templates` and the shell
singletons recorded in
[`docs/research/OMARCHY_ARCHITECTURE.md`](../research/OMARCHY_ARCHITECTURE.md).
This document supersedes the Session 9 draft, which hedged upstream claims as
*"inspiration, not verified"*; those hedges are now resolved into verified
facts or explicitly corrected.

## Why Omni uses Omarchy as research

Omarchy solves the same abstract problem Omni does — one semantic palette,
rendered into per-application configuration, switched safely and reversibly,
with third-party themes kept from executing code — but on a different desktop
(Hyprland + the Quickshell-based `omarchy-shell`). The mechanisms that matter
are desktop-neutral and were built and battle-tested in production:

* clean staging, atomic promotion, single-writer serialization;
* user overlays and user templates with a fixed precedence order;
* provenance-based filtering of cloned themes;
* a palette/surface split that keeps "what the colors are" separate from
  "how surfaces use them".

Reading a working system and adapting its verified design is more reliable
than inventing these mechanisms from scratch. Where the desktop differs
fundamentally (compositor config vs. Plasma's own layers), Omni diverges
deliberately rather than porting.

## What Omni borrowed

All left-column facts below are **verified upstream** (see provenance above):
first-party themes live under `themes/<name>/` (installed at
`/usr/share/omarchy/themes/<name>/`) with optional user themes under
`~/.config/omarchy/themes/<name>/`; `omarchy-theme-set` stages into
`~/.local/state/omarchy/current/next-theme` and promotes into
`current/theme`, writing `theme.name`; runs serialize on a `flock`; user
templates `~/.config/omarchy/themed/*.tpl` render before the built-in
`default/themed/*.tpl` and a built-in output is skipped when a user template
produces the same filename; existing staged files are never overwritten by a
template, so hand-written theme files win over generated output; the
`theme-set` hook fires after activation.

| Verified Omarchy idea | Where it lands in Omni |
|---|---|
| One semantic `colors.toml` per theme (accent/selection/muted → backgrounds → foregrounds → named colors; legacy short-name aliases) | `themes/*/colors.toml`, `SEMANTIC_ROLES` in `core/theme_model.py` |
| Surface/style roles separated from the palette (`shell.toml`, consumed by the shell's `Color`/`Style` QML singletons) | `surfaces.toml` as an **adapter-neutral** surface model (see [Why surfaces.toml remains](#why-surfacestoml-remains)) |
| Template-driven generation from the palette; `{{ key }}`, `{{ key_strip }}`, `{{ key_rgb }}`, `mix`/`mix_strip`/`mix_rgb` | `core/renderer.py` (Omni adds `kde_gradient` and strict, reportable errors) |
| Two theme roots, user overlay applied at staging; missing user dir is a no-op | `load_theme_with_overlay()` deep merge of `~/.config/omni-theme/themes/<name>/` |
| User templates before built-ins; same output name ⇒ built-in skipped | template resolution order user → theme → built-in (`core/renderer.py:resolve_template`, used by `core/staging.py`) |
| Hand-written theme files beat generated template output | theme-tier templates and overlay provenance reporting (`OverlayReport`) |
| `next-theme` staging + atomic promotion; consumers never see torn state | generations + atomic pointer swap (`core/state.py`) |
| `flock` serialization of theme switches | (in spirit) single state-dir staging; **Omni does not yet add a cross-process lock — recorded gap** |
| Post-promotion hooks keep adapters decoupled (`theme-set` hook) | lifecycle events (`core/events.py`); a `hooks/` directory is reserved |
| Provenance denylist for git-cloned themes (`*.lua`, terminal configs that name programs, `vscode.json`, all symlinks; dropped files named on stderr; filtering at staging so later `git pull`s are covered; explicitly a provenance statement, not a sandbox) | same stance: themes are data, inert template grammar, declared targets; **Omni's installer + denylist filtering is not yet implemented** (see OWNERSHIP_AND_SECURITY.md) |
| `mode` selection with `light.mode` marker-file legacy support | Omni accepts `mode = "dark"\|"light"` in TOML only (marker file rejected) |

## What Omni intentionally changed

* **The sed-script renderer** — upstream renders by generating a `sed`
  script over palette pairs. Omni replaced it with a parsed, strict template
  engine (`tomllib` + a closed helper set, zero dependencies) so malformed
  templates and values fail with file/line/error context instead of
  silently corrupting output.
* **Whole-file overlay granularity → key-level deep merge.** Upstream
  overlays whole files (a user `shell.toml` replaces the system one). Omni
  merges overlay `colors.toml`/`surfaces.toml` **key-by-key** and reports
  exactly which keys the user owns (`OverlayReport`), so "tweak one value"
  does not require copying the whole file.
* **Single `current/theme` → immutable generations + rollback.** Upstream
  keeps one materialized active theme per switch. Omni keeps immutable
  generations, a pointer swap, per-target ownership hashes, and byte-exact
  rollback of owned targets.
* **Desktop retint model.** Upstream dispatches a parallel list of
  per-app restart/retint commands (`post_theme_commands`) and pushes payloads
  to its shell over IPC. Omni applies through KDE's own tooling and relies on
  Plasma's change notification; no IPC theme push, no OSC live retinting.
* **Validation as data** (WCAG 2.x contrast thresholds, required-role checks,
  strict surface-value grammar via `omni theme validate`) and an explicit
  **adapter contract** (capability probes, skip-and-report, criticality,
  per-phase results) are Omni additions with no upstream equivalent needed on
  a single-shell desktop.
* **`light.mode` legacy** — upstream supports a legacy empty marker file;
  Omni accepts `mode` in TOML only.

## Why KDE needs adapters

On Omarchy's desktop, theme files *are* the application configuration: write
the staged file, restart or signal the consumer. Verified upstream, that is
the `post_theme_commands` retint list plus Hyprland picking up staged theme
files as Lua modules.

KDE Plasma 6 is different in kind, not degree:

* the Color Scheme (`plasma-apply-colorscheme`), Plasma Style, wallpaper
  (`plasma-apply-wallpaperimage`) and panel layout each have their own
  storage, tools and notification semantics;
* `kdeglobals` is KDE's own user state — Omni only ever reads it back for
  verification, never writes it by hand;
* GTK, Konsole and VS Code each follow separate conventions.

No single file copy can switch a Plasma desktop, so Omni routes each surface
through an adapter that probes capabilities, applies through the surface's
official mechanism, verifies, and either succeeds or reports a skip/failure
with explicit criticality. An unsupported surface degrades gracefully instead
of failing the activation.

## Why shell.json is not reproduced

Verified upstream (`shell/README.md`): `omarchy-shell` is a single
long-running **Quickshell** instance hosting the Omarchy desktop; plugins
(bar widgets, panels, overlays, menus, services, full bars) ship a
`manifest.json`; and `~/.config/omarchy/shell.json` is the one user config
file that owns the bar layout, per-entry settings, enabled-plugin list and
idle timings — authoritative once customized, with an IPC contract
(`summon`/`rescanPlugins`/`listPlugins`, …) around it.

That file belongs to Omarchy's shell, and Omni's target desktop has no such
file: on KDE Plasma, panel/widget/window layout is owned by plasmashell's own
configuration and is edited through Plasma itself. Omni themes **colors**, not
layout; reproducing a plugin manifest, registry or IPC system would amount to
rebuilding a desktop shell — deliberately out of scope. Omni neither reads,
writes, nor emulates `shell.json` or any plugin state in any form.

## Why surfaces.toml remains

Omarchy's `shell.toml` proves that a surface/style layer separated from the
palette works (verified section model, borders that accept a solid color or a
gradient in one key, `-alpha` companions, CSS-style border-width lists,
per-side and state-specific overrides, `[controls]` state machines). Omni
keeps the *idea* as data but does **not** copy the Quickshell consumer
contract. These four things are related and **not one-to-one equivalents**:

| Model | System | What it is |
|---|---|---|
| `surfaces.toml` (Omni) | Omni engine | adapter-neutral semantic surface model: `group → key → value` (e.g. `popups`, `controls`) consumed by templates and adapters |
| `shell.toml` (Omarchy) | Omarchy Quickshell shell | shell-specific surface/style roles consumed by the `Color`/`Style` QML singletons |
| `shell.json` (Omarchy) | Omarchy Quickshell shell | shell configuration: bar layout, per-entry settings, enabled plugins |
| native Plasma config | KDE Plasma | panel/widget/window configuration owned by plasmashell |

`surfaces.toml` stays because surface styling (popup chrome, control states,
borders) is desktop-neutral *as data*, while every consumer of it is
desktop-specific. The verified Omarchy border language (solid-or-gradient in
one key, alpha companions, width lists) is mirrored in Omni's surface grammar
(`core/color.py` value classification, the `kde_gradient` template helper)
and re-expressed per adapter — not bound to any shell implementation.
Removing `surfaces.toml` in favour of a shell-specific model would couple
Omni's theme format to a shell Omni does not target.

## What is explicitly out of scope

* **Hyprland** — the compositor, `hyprctl reload`, `hyprland.lua` and all
  Hyprland Lua module loading. Omni targets KDE Plasma 6's own layers.
* **Quickshell and the QML shell** — no shell replacement, no `omarchy-shell`
  IPC (`shell applyTheme`, `summon`, …), no plugin manifest/registry system,
  no `shell.json` in any form.
* **Plasma shell layout** — panel/widget/applet configuration belongs to
  plasmashell; Omni never writes it.
* **`kdeglobals` direct writes, Plasma Style, Global Themes, `kwinrc`** —
  outside the adapter's remit (Color Scheme + wallpaper, verified via
  read-back); KWin scripts are permanently out of scope.
* **IPC theme push and OSC live retinting of open panes** — running apps are
  notified by KDE's own apply tools; where a surface needs a restart, that is
  the surface's documented behaviour (see `docs/research/KDE_PLASMA_6.md`).
* **Whole-desktop snapshot switching** — Omni records per-target ownership
  hashes instead of snapshotting `~/.config`.

## Compatibility note

The `colors.toml` convention is shared with Omarchy-style themes, so an
Omarchy palette can be dropped into `themes/<name>/colors.toml` and parsed
directly (`tomllib`), subject to Omni's required-role validation — a theme
needs the full semantic role set (see [THEME_MODEL.md](THEME_MODEL.md))
before it will validate.
