# Architecture Decisions — omni-theme-cachy (Session 01)

Status: decided in Session 01; revisable through `docs/architecture/` ADRs
later. Each decision states the rationale and the rejected alternative.

## Product shape

A universal theming engine for CachyOS + KDE Plasma 6, inspired by Omarchy's
engine design but for a **traditional floating-window, mouse-driven desktop**:
no tiling assumptions, no shell-replacement — Plasma stays Plasma. One
semantic palette drives every supported surface (color scheme, Plasma style,
wallpaper, GTK, terminals, editors) via generated artifacts.

## Why TOML?

- Human-authored palette files need comments, ordering stability and quoting
  rules; INI/JSON/YAML each fail one of these (JSON: no comments; YAML: the
  Norway problem + footguns; INI: no standard parser).
- Python 3.11+ ships `tomllib` (read) in stdlib → **zero runtime dependency**
  on this Arch/CachyOS box.
- Omarchy precedent means a large ecosystem of themes already speaks
  `colors.toml`; compatibility is free.
- Rejected: YAML (parser safety), JSON (no comments), custom DSL
  (maintenance cost with no gain).

## Why Python?

- Present at 3.14.7 on the target; stdlib covers TOML parsing, templating
  (`string.Template`), colour math, subprocess, pathlib, shutil, tempfile,
  fcntl-style locking via `os`/`fcntl`.
- The KDE application layer is subprocess-driven anyway (`plasma-apply-*`,
  `kwriteconfig6`, `qdbus6`); Python orchestrates that cleanly.
- Rejected: bash (no data structures worth the pain; upstream Omarchy outgrew
  it too), Rust/Go (compile step unjustified for config generation),
  Node/other runtimes (not guaranteed present).

## Why a semantic theme model?

Templates must not hardcode `color4`; they should ask for *roles* — accent,
background, foreground, muted, red… plus the ANSI ramp as data. Benefits:

1. One theme definition renders every target app correctly.
2. Light/dark handled by declared `mode`, mirroring Plasma's own scheme
   polarity.
3. Legacy/short aliases can resolve to canonical roles without breaking old
   templates (Omarchy-compatible mapping).
4. Colour derivations (`selection = mix(background, accent, 20%)`) become
   possible centrally instead of copy-pasted per app.

## Why adapters?

Every target app has its own artifact format and apply mechanism:

| Adapter | Generates | Applies via |
|---------|-----------|-------------|
| kde-colorscheme | `<Name>.colors` | `plasma-apply-colorscheme` |
| kde-plasmastyle | desktoptheme dir or selection | `plasma-apply-desktoptheme` |
| kde-wallpaper | image path / kpackage | `plasma-apply-wallpaperimage` |
| gtk | `gtk.css`, settings.ini | gsettings / file drop |
| terminal/editor/etc. | rendered templates | file drop + optional reload cmd |

Adapters are self-declared, individually enable/disable-able (Stylix lesson),
and isolated: one broken adapter must never abort the whole activation. The
engine core knows nothing about any specific app.

## Why staging?

Activation composes many writes: overlay user theme, render N templates,
generate M artifacts. Doing this in-place risks half-themes on failure
(partially applied state — the exact pywal weakness). Staging builds the
complete next-theme under `$XDG_STATE_HOME/omni-theme/current/staging/`
(never inside Git, never inside live config), validates it, then promotes.

## Why atomic activation?

Promotion is a single rename/symlink-swap of the staging directory onto
`current/theme` (same filesystem ⇒ atomic `os.replace`). Consumers only ever
see a complete directory. Combined with hooks firing strictly after promotion,
a crashed switch leaves either the old or the new theme — never a mixture.

## Why runtime state outside Git?

- Git holds authored content: palettes, templates, hooks, docs.
- Runtime state (current theme pointer, last-good snapshot, logs, lock file)
  lives in `$XDG_STATE_HOME/omni-theme/` — machine-local, disposable,
  potentially large (theme snapshots), and semantically not source.
- This mirrors Omarchy (`~/.local/state/omarchy/…`) and keeps `git status`
  meaningful.

## How do user overrides work?

Precedence, highest first:

1. **User hand-written files** in `~/.config/omni-theme/themes/<name>/` —
   staged in full; templates never overwrite an existing staged file.
2. **User templates** `~/.config/omni-theme/templates/*.tpl` — same output
   filename suppresses the built-in template (Omarchy rule).
3. **Repo theme files** `themes/<name>/`.
4. **Rendered built-in templates** `templates/*.tpl`.

So a user can override one value, one file, or one template without touching
the repo — and updates to the repo never clobber their choices.

## How does file ownership work?

The engine owns only what it generated or promoted:

- Generated artifacts carry a header comment naming the engine + source
  template + theme; adapters refuse (with guidance) to overwrite a foreign
  file lacking our header unless `--force`.
- Managed paths are recorded in the current-theme manifest written into
  `$XDG_STATE_HOME/omni-theme/current/theme.json`; rollback/cleanup uses that
  manifest, never globbing guesses.
- Files outside the manifest are never modified by uninstall/reset.

## How does rollback work?

Before promotion, the previous complete theme directory is retained as
`$XDG_STATE_HOME/omni-theme/previous/`. Rollback re-promotes it and re-runs
adapter apply steps (artifacts regenerate deterministically from the stored
manifest). Because generation is pure (palette + templates → bytes), rollback
is byte-exact even after template edits — we keep the manifest + previous
staging, not diffs.

## How do unsupported integrations behave?

Unknown/failed adapters are **non-fatal**: log a warning, continue remaining
adapters, report a summary at exit (`applied / skipped / failed`). A theme is
never left half-promoted because one app's apply command failed; the theme
data itself is fully promoted atomically, and per-app application retries are
safe (idempotent CLI tools).

## How are third-party themes prevented from executing arbitrary code?

Omarchy's provenance model, tightened:

1. Themes installed via our installer (git clone) are marked untrusted
   (presence of `.git`); hand-written user dirs are trusted.
2. Untrusted themes stage through a **denylist of executable-content files**
   (scripts, `.lua`, editor plugin manifests, terminal configs naming binaries,
   anything with the exec bit set) and all **symlinks are dropped at any
   depth**; dropped items are named on stderr.
3. Only colour/config *data* survives; anything dropped regenerates from
   templates.
4. **Hooks execute only from the trusted repo/hook directories** — never from
   a theme directory. Templates are inert text; the renderer performs plain
   substitution with a closed set of filters, so no template can invoke code.
5. A test enforces classification of every shipped template (code vs colour)
   so new templates cannot silently bypass policy.

This is provenance filtering, not sandboxing — documented honestly, as
upstream does.

## Consequences / follow-ups

- Session 02+: implement `core/` (palette load, colour math, renderer,
  staging), then `adapters/kde_colorscheme.py` first (highest visible impact).
- Every adapter ships a dry-run mode before Session 03 touches live config.
