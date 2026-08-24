# Environment Research — Session 01

Recorded on the actual target machine. Nothing here is assumed; every value was
observed by running the commands listed in the session brief.

## Machine

| Item | Value |
|------|-------|
| `uname -a` | `Linux tlap 7.2.0-rc7-1-cachyos-rc #1 SMP PREEMPT_DYNAMIC Mon, 10 Aug 2026 20:51:00 +0000 x86_64 GNU/Linux` |
| `/etc/os-release` | `NAME="CachyOS Linux"`, `ID=cachyos`, `ID_LIKE=arch`, `BUILD_ID=rolling` |
| Desktop | `XDG_CURRENT_DESKTOP=KDE`, plasmashell **6.7.4** |
| Session type | `wayland` |
| Python | 3.14.7 (`python` and `python3`) |
| Git | 2.55.0 |

## XDG paths (as seen in this shell)

| Variable | Observed value | Consequence for the engine |
|----------|----------------|----------------------------|
| `HOME` | `/home/tariq` | — |
| `XDG_CONFIG_HOME` | *(unset)* | Default to `$HOME/.config`. Never assume it is set. |
| `XDG_DATA_HOME` | *(unset)* | Default to `$HOME/.local/share`. |
| `XDG_STATE_HOME` | `/home/tariq/.config/ai.opencode.desktop` | **Polluted by a third-party tool in this shell.** The engine must apply the XDG default (`$HOME/.local/state`) rather than blindly trusting the environment, or at minimum validate that the path is a plausible state root. |

## KDE tooling inventory

All commands verified with `command -v`:

| Tool | Status | Path |
|------|--------|------|
| `plasma-apply-colorscheme` | FOUND | `/usr/bin/plasma-apply-colorscheme` |
| `plasma-apply-desktoptheme` | FOUND | `/usr/bin/plasma-apply-desktoptheme` |
| `plasma-apply-wallpaperimage` | FOUND | `/usr/bin/plasma-apply-wallpaperimage` |
| `plasma-apply-lookandfeel` | FOUND | `/usr/bin/plasma-apply-lookandfeel` |
| `qdbus6` | FOUND | `/usr/bin/qdbus6` (`qdbus` and `qdbus-qt6` are absent) |
| `kreadconfig6` / `kwriteconfig6` | FOUND | `/usr/bin/kreadconfig6`, `/usr/bin/kwriteconfig6` |
| `kbuildsycoca6` | FOUND | `/usr/bin/kbuildsycoca6` |
| `lookandfeeltool` | FOUND (legacy alias) | `/usr/bin/lookandfeeltool` |

## CLI interfaces verified locally (`--help`)

- `plasma-apply-colorscheme <name>` — applies scheme; `-l/--list-schemes`;
  `-a/--accent-color <SVG name | hex>`.
- `plasma-apply-desktoptheme <name>` — Plasma style; `--list-themes`.
- `plasma-apply-wallpaperimage <file>` — image wallpaper;
  `-f/--fill-mode <mode>` (e.g. `preserveAspectCrop`).
- `plasma-apply-lookandfeel -a <pkg>` — global theme packages; `-l`,
  `-k/--keep-auto`, `--resetLayout`.

## Live reload surface (verified)

- plasmashell runs as a **systemd user unit**: `plasma-plasmashell.service`
  (active). Restart via
  `systemctl --user restart plasma-plasmashell.service`.
- DBus `org.kde.plasmashell /PlasmaShell` exposes:
  - `org.kde.PlasmaShell.refreshCurrentShell()` — soft refresh.
  - `org.kde.PlasmaShell.setWallpaper(QString plugin, QVariantMap params, uint screen)` —
    programmatic wallpaper without touching appletsrc by hand.
  - `wallpaper(uint screen)`, `colorChanged(QString)` signal.

## Current desktop state (snapshot)

- ColorScheme: `SweetAmbarBlue`; accent: `AccentColor=90,197,239`;
  `ColorSchemeHash=47ec8c6b…` present in `~/.config/kdeglobals`.
- Widget style: `Breeze`; KWin decoration section present in `~/.config/kwinrc`
  (`BorderSize=None`).
- User has ~20 color schemes, ~20 desktop themes, ~20 look-and-feel packages,
  and several wallpaper packs under `~/.local/share/…` — real-world data the
  engine must coexist with, never clobber.

## Theme package locations observed on disk

| Kind | System | User |
|------|--------|------|
| Color schemes | `/usr/share/color-schemes/*.colors` (incl. CachyOS ones) | `~/.local/share/color-schemes/*.colors` |
| Plasma styles (desktoptheme) | `/usr/share/plasma/desktoptheme/<name>/` | `~/.local/share/plasma/desktoptheme/<name>/` |
| Global themes (look-and-feel) | — | `~/.local/share/plasma/look-and-feel/<name>/` |
| Wallpapers | — | `~/.local/share/wallpapers/…` |

Both packaging generations coexist in user data: `Nordic` desktoptheme ships a
legacy `metadata.desktop`, while `Sweet` look-and-feel ships KPackage
`metadata.json` (`"KPackageStructure": "Plasma/LookAndFeel"`). The engine must
tolerate both when inspecting installed packages.

## Implications

1. Zero-dependency Python 3.14 is viable: `tomllib` is stdlib since 3.11.
2. Prefer KDE's own CLI tools over hand-editing `kdeglobals` (see
   `KDE_PLASMA_6.md` — `ColorSchemeHash` makes manual rewriting fragile).
3. Always resolve XDG dirs through defaults, never trust raw env vars.
4. Hooks can use `qdbus6` (not `qdbus`) on this system.
