# Session 05 — KDE Plasma 6 Adapter, Color Scheme, Surface Mapping, and Wallpaper

## Objective

Implement the first real desktop integration: KDE Plasma 6.

This session must be based on current KDE Plasma 6 behavior, not KDE 5 memory.

Current KDE documentation distinguishes Color Scheme, Plasma Style, Global Theme, wallpaper/plasma scripting, and user-installed theme locations. A Color Scheme is an INI-style color definition and is normally installed for users under `~/.local/share/color-schemes/`. KDE documentation also states that applying a Color Scheme copies its values into `~/.config/kdeglobals` and that `kde-gtk-config` can synchronize colors into the Breeze GTK configuration. citeturn325344search0

Do not implement Plasma Style or Global Theme in this session.

## Prerequisites

Session 04 complete.

Inspect actual environment before implementation:

```bash
plasmashell --version
echo "$XDG_CURRENT_DESKTOP"
echo "$XDG_SESSION_TYPE"
command -v plasma-apply-colorscheme || true
command -v kreadconfig6 || true
command -v kwriteconfig6 || true
command -v kpackagetool6 || true
command -v qdbus6 || true
command -v qdbus || true
```

## OpenCode tool contract

Use:

- `read`
- `glob`
- `grep`
- `bash`
- `edit`
- `write`
- `lsp`
- `websearch` and `webfetch` before implementing behavior whose current Plasma 6 semantics are uncertain

Free/open-source CLI tools:

```bash
rg
fd
jq
python
pytest
git
```

Use KDE-native tools when actually installed; never assume `qdbus6` exists.

## Critical design boundaries

```text
Omni Theme Model
        |
        +--> KDE Color Scheme adapter
        |
        +--> Wallpaper adapter
        |
        +--> future Plasma Style adapter
        |
        +--> future Global Theme adapter
```

Do not collapse these into one "KDE theme" operation.

KDE explicitly describes:

- Color Scheme: colors for KDE/Qt applications and Plasma UI that respects it.
- Plasma Style: visual styling of panels, widgets, OSD, lock/logout screens.
- Global Theme: a package that can bundle several components. citeturn325344search0turn325344search1

## Step 1 — Inspect current code

Read:

```text
core/events.py
core/activation.py
core/engine.py
core/theme_model.py
core/renderer.py
core/filesystem.py
core/targets.py
```

Inspect any existing `adapters/` modules.

Determine actual adapter registration pattern.

Do not create a second competing plugin architecture.

## Step 2 — KDE adapter structure

Preferred structure:

```text
adapters/kde/
    __init__.py
    adapter.py
    colors.py
    wallpaper.py
    detection.py
    config.py
```

Adapt to repository conventions.

The adapter should expose:

```text
capability()
plan()
render()
apply()
verify()
rollback()
```

It must subscribe to the core lifecycle/event system instead of being called directly from the core engine.

## Step 3 — Color Scheme generation

Generate:

```text
~/.local/share/color-schemes/<safe-id>.colors
```

Use a controlled project-owned filename.

Do not write arbitrary user-provided paths.

The generated format must be verified against real Plasma 6 examples before implementation.

At minimum investigate and test standard sections such as:

```text
[Colors:Window]
[Colors:View]
[Colors:Button]
[Colors:Selection]
[Colors:Tooltip]
[Colors:Complementary]
```

Do not invent KDE keys.

Build a mapping table in code, for example:

```python
KDE_COLOR_MAP = {
    "background": ...,
    "foreground": ...,
    "accent": ...,
}
```

The mapping must be explicit and testable.

## Step 4 — Surface role mapping

Keep `surfaces.toml` as Omni's semantic abstraction.

Do not describe it as an exact copy of Omarchy `shell.toml`.

Reason:

- Omarchy's `shell.toml` contains Quickshell-specific surface/layout concepts.
- KDE Plasma owns panel/widget/window behavior differently.
- Omni's `surfaces.toml` is an adapter-neutral model.

Map only semantically meaningful roles that KDE actually supports.

Example:

```text
surfaces.popups.background
    -> KDE tooltip/complementary background where appropriate

surfaces.controls.normal-border
    -> KDE button/selection colors where a genuine mapping exists
```

For unsupported semantics:

```text
status = unsupported
reason = "KDE Color Scheme has no direct equivalent"
```

Never invent a configuration key just to make the mapping appear complete.

## Step 5 — Apply Color Scheme

Detect:

```bash
command -v plasma-apply-colorscheme
```

If available, use the native utility.

If unavailable:

- report capability accurately;
- determine whether KDE's documented configuration path can be used safely;
- do not shell out to guessed/legacy commands.

Do not require a command merely because it existed on an older KDE release.

## Step 6 — Ownership of kdeglobals

Remember that applying a KDE Color Scheme affects user configuration.

Do not treat `~/.config/kdeglobals` as a normal generated file that Omni can blindly overwrite.

The adapter must distinguish:

```text
generated Color Scheme package
```

from:

```text
KDE user state produced by applying that scheme
```

Only the former is directly owned by Omni unless an explicit, well-tested ownership policy is designed.

## Step 7 — Wallpaper

Implement:

```bash
omni wallpaper list
omni wallpaper current
omni wallpaper set <path>
```

But the underlying mechanism must be researched against current Plasma 6.

KDE's Plasma scripting API documents changing wallpaper through desktop/containment configuration, including the `org.kde.image` wallpaper plugin and `Image` configuration key. citeturn325344search5turn325344search8

Do not hard-code a DBus path before verifying the actual installed session.

Preferred process:

```text
source path
   -> validate image
   -> copy into Omni-owned cache/state location
   -> establish stable internal path
   -> set wallpaper through the safest available Plasma mechanism
   -> verify actual active wallpaper
```

The cached copy prevents a theme from pointing at a source file the user later moves.

Do not silently delete prior user wallpapers.

## Step 8 — Plasma Style boundary

Do not implement:

```text
~/.local/share/plasma/desktoptheme/
```

in this session.

Only record capability detection.

KDE documents user-installed Plasma Styles under `~/.local/share/plasma/desktoptheme/`; Plasma 6 theme packaging has its own KPackage rules and should be handled as a later adapter. citeturn325344search0turn325344search2turn325344search3

## Step 9 — Reload/verification

Do not restart the whole desktop.

Verify:

```text
Color Scheme is installed
Color Scheme is selected
Wallpaper is set
Wallpaper survives adapter verification
```

For each native command used, record:

```text
command
required binary
Plasma version tested
success criteria
failure behavior
```

## Step 10 — Tests

Create:

```text
tests/unit/test_kde_colors.py
tests/unit/test_kde_detection.py
tests/unit/test_kde_wallpaper.py
tests/integration/test_kde_adapter.py
```

Unit tests must run on machines without KDE.

Integration tests should:

```python
pytestmark = pytest.mark.kde
```

or equivalent and skip cleanly when the environment is not KDE Plasma 6.

Never alter the real user's theme during ordinary CI/unit tests.

## Step 11 — Real-machine verification

Only after unit tests pass:

```bash
omni theme preview default --json
omni theme apply default --dry-run --json
```

Then, after confirming no conflicts:

```bash
omni theme apply default --yes
omni status --json
omni theme current
```

Check KDE manually.

Then test:

```bash
omni theme rollback --yes
```

Do not claim success if only files were generated.

## Exit condition

KDE Color Scheme and wallpaper must either be:

- actually verified on the target KDE Plasma 6 environment; or
- explicitly reported as unverified with the exact blocker.

## Commit

```bash
git add adapters/kde tests docs
git commit -m "feat: add KDE Plasma 6 color scheme and wallpaper adapter"
```
