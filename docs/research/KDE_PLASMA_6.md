# KDE Plasma 6 — Research Notes (Session 01)

Sources: KDE developer docs (develop.kde.org, docs.kde.org), KDE Discuss
threads, plasma-workspace source commits, plus **local inspection on the
target machine (Plasma 6.7.4)**. CLI behaviour below was verified with
`--help` and live DBus introspection, not copied from memory.

## The critical distinction: Color Scheme ≠ Plasma Style ≠ Global Theme

| Concept | What it styles | File/package | Applied by |
|---------|----------------|--------------|-----------|
| **Color Scheme** | Qt widget + app palette (all `Colors:*` roles) | `<Name>.colors` INI in `$XDG_DATA_HOME/color-schemes/` | `plasma-apply-colorscheme` |
| **Plasma Style** | Shell chrome: panel, widgets, popups (SVGs) | KPackage dir under `…/plasma/desktoptheme/<name>/` | `plasma-apply-desktoptheme` |
| **Global Theme** (look-and-feel) | Bundle that sets colorscheme + plasmatheme + icons + cursors + splash + window deco + defaults | KPackage dir under `…/plasma/look-and-feel/<id>/` | `plasma-apply-lookandfeel -a <pkg>` |
| **Window decoration** | Titlebars/buttons | Aurorae svg or native KWin lib theme | keys under `[org.kde.kdecoration2]` in `kwinrc` |

A theming engine must treat these as *separate adapters*: applying a global
theme is a blunt instrument that resets layout-adjacent state
(`--resetLayout`) and overrides individual choices; precise engines set each
layer individually.

## Color scheme file format

`.colors` is a KConfig INI:

```ini
[General]
ColorScheme=SweetAmbarBlue     # display name

[Colors:View]                  # sets: Window, Button, View, Selection,
BackgroundNormal=30,30,38      # Tooltip (+ Header/Complementary in P6)
BackgroundAlternate=…
ForegroundNormal=…

[ColorEffects:Disabled]        # per-state effect params
ColorEffect=0
```

- Sets observed in real files on this machine: `Colors:View`, `Colors:Window`,
  `Colors:Button`, `Colors:Selection`, `Colors:Tooltip`,
  `Colors:Complementary`, `Colors:Header`; effects groups
  `ColorEffects:{Disabled,Inactive}`.
- Colors are comma-separated RGB ints; alpha via a 4th component where used.

## How application works (and why we must not hand-roll it)

`plasma-apply-colorscheme`:

1. copies the `.colors` groups into `kdeglobals` (`[Colors:*]`,
   `[ColorEffects:*]`),
2. writes `[General] ColorScheme=<name>`,
3. computes and stores `ColorSchemeHash=sha1(file bytes)` — running Qt apps
   use it to detect palette changes; a hand-computed mismatch makes already-
   running apps keep stale colors (documented failure mode of DIY switchers),
4. emits D-Bus/KConfig change notifications so open apps repaint live.

**Decision:** our engine shells out to `plasma-apply-colorscheme` for
application. We only *generate* `.colors` files. Same principle for
desktoptheme/wallpaper/lookandfeel tools. Accent color:
`plasma-apply-colorscheme -a '#hex'`.

Accent color is also readable via the freedesktop Settings portal
(`org.freedesktop.appearance` `accent-color`).

## Plasma Style (desktoptheme) package

Observed layout (`~/.local/share/plasma/desktoptheme/Nordic/`):

```
Nordic/
├── metadata.desktop        ← legacy descriptor (still loaded by 6.7!)
│   └── [Desktop Entry] X-KDE-PluginInfo-Name=Nordic …
├── dialogs/  icons/  widgets/   ← SVG sets
├── colors                  ← optional plasma-scheme color overrides file
└── solid/ preview/
```

Plasma 6 canonical packaging is a **KPackage**: `metadata.json` with
`"KPackageStructure": "Plasma/LookAndFeel"` (look-and-feel) or the desktop
theme equivalent, plus `contents/…`. Both generations coexist on this system;
new packages we generate should use `metadata.json`.

SVGs can follow the color scheme via the `hint-apply-color-scheme` element or
CSS classes (`ColorScheme-Text`, `ColorScheme-Highlight`, …) inside a
`<style id="current-color-scheme">` block — accent-aware elements use class
`ColorScheme-Highlight` with `fill/stroke="currentColor"`.

## Global Theme (look-and-feel) package

Verified locally at `~/.local/share/plasma/look-and-feel/Sweet/`:

```
Sweet/
├── metadata.json           { "KPackageStructure": "Plasma/LookAndFeel", "KPlugin": { "Id": "Sweet", … } }
└── contents/
    ├── defaults            ← maps global theme → components:
    ├── previews/             [kdeglobals][KDE] widgetStyle=kvantum
    └── splash/               [kdeglobals][General] ColorScheme=Sweet
                               [kdeglobals][Icons] Theme=candy-icons
                               [kcminputrc][Mouse] cursorTheme=Sweet-cursors
                               [plasmarc][Theme] name=Sweet
                               [kwinrc][org.kde.kdecoration2] library/theme=aurorae Sweet-Dark
```

The `contents/defaults` mapping is exactly the "one semantic theme → many app
layers" idea, expressed in KDE's own format.

## Wallpaper mechanisms (Plasma 6)

1. `plasma-apply-wallpaperimage <file>` — simplest supported path; accepts an
   image or installed wallpaper kpackage; `-f` fill mode.
2. DBus: `org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.setWallpaper`
   `(plugin, QVariantMap parameters, screen)` — per-screen programmatic control.
3. Persisted state lives in
   `~/.config/plasma-org.kde.plasma.desktop-appletsrc` under
   `[Containments][n][Wallpaper][org.kde.image][General] Image=…` — read-only
   reference for us; never edit by hand when a tool exists.
4. Wallpapers can also be packaged as kpackages in
   `$XDG_DATA_HOME/wallpapers/` (observed on this machine).

## Reload / restart behaviour

| Layer | Live? | Mechanism |
|-------|-------|-----------|
| Color scheme | Yes, running Qt apps auto-repaint | KConfig notify from `plasma-apply-colorscheme` |
| GTK apps | Partially | xsettingsd / gsettings bridges; some apps need restart |
| Plasma style | Mostly | plasmashell picks up on refresh; full fidelity via restart |
| Panel/layout-affecting changes | No | `systemctl --user restart plasma-plasmashell.service` |
| Icon caches | — | `kbuildsycoca6` after icon theme changes |

Verified present on this machine: systemd user unit `plasma-plasmashell.service`
(active) and `qdbus6 org.kde.plasmashell /PlasmaShell` methods
`refreshCurrentShell()`, `setWallpaper(...)`.

## Packaging / installation conventions (Plasma 6)

- User scope: `$XDG_DATA_HOME` = `~/.local/share`
  - `color-schemes/*.colors`
  - `plasma/desktoptheme/<name>/`
  - `plasma/look-and-feel/<reverse-fqdn-or-name>/`
  - `wallpapers/…`, `icons/<name>/`, `aurorae/themes/<name>/`
- System scope mirrors these under `/usr/share/`.
- `kpackagetool6` handles install/list/uninstall of KPackage-style themes.
- CachyOS ships its own themes (`CachyOS-Nord-*`, `cachyos-emerald*`,
  `Emerald*`, `Iridescent*` seen in `/usr/share`) — engine must coexist, not
  fight the distro defaults.

## Implications for our engine

1. Generate artifacts into XDG user data; apply via official CLI tools.
2. One `.colors` generator adapter + one wallpaper adapter covers the most
   visible 80% of a KDE retint without touching global themes.
3. Restart plasmashell only as a last-resort hook step, not per-layer.
