# Getting Started

Requirements: Linux with **KDE Plasma 6** (target platform: CachyOS),
Python **3.11+**. Zero runtime dependencies beyond the stdlib; `pytest`
is the only dev extra.

## Install (one command, no sudo)

`install.sh` creates a dedicated virtualenv, installs the engine into it,
and exposes both executables — `omni` and `omni-theme` — through
`~/.local/bin`. It never uses `sudo` and never touches system Python.

**Reviewable clone + installer (recommended):**

```bash
git clone https://github.com/Tariq-Anjum/omni-theme-cachy.git
cd omni-theme-cachy
bash install.sh
```

**One-command convenience form:**

```bash
curl -fsSL https://raw.githubusercontent.com/Tariq-Anjum/omni-theme-cachy/main/install.sh | bash
```

Piping a remote script straight into bash runs code you have not read.
You may inspect it first — the same file, unmodified:

```bash
curl -fsSL https://raw.githubusercontent.com/Tariq-Anjum/omni-theme-cachy/main/install.sh -o install.sh
less install.sh    # review, then: bash install.sh
```

If you prefer to read before running, use the git-clone method above.

**Manual / local install (development and CI):**

```bash
OMNI_SOURCE_DIR=/path/to/checkout bash install.sh   # install from an existing checkout; never clones
# or entirely by hand:
python -m venv ~/.venvs/omni-theme
~/.venvs/omni-theme/bin/pip install /path/to/checkout
```

Re-running the installer is safe. An existing managed clone at
`~/.local/share/omni-theme-cachy` is fast-forwarded to `origin/main`
only when it is clean; if it has local modifications the installer
refuses and preserves them. `OMNI_INSTALL_DIR` and `OMNI_BIN_DIR`
override the clone and shim locations.

After installing, ensure `~/.local/bin` is on your `PATH`:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc   # then: source ~/.bashrc
```

## First check

```bash
omni version                # package + state schema version
omni doctor                 # environment diagnostic (read-only)
omni doctor --json | jq .   # machine-readable variant
```

`doctor` reports your Plasma version, session type, required binaries
(`plasma-apply-colorscheme`, `kreadconfig6`, `qdbus6`, …), XDG roots,
write permissions and per-adapter capability. It never writes anything.

Theme discovery note: by default the engine finds themes in a `themes/`
directory relative to your current directory; point it anywhere with
`--root` (e.g. a checkout, or a directory of downloaded themes).

## Look before you leap

```bash
omni theme list                     # discover themes
omni theme validate default         # rule-check a theme
omni theme preview default --json   # the exact plan: targets, conflicts, capabilities
omni theme apply default --dry-run --json   # same plan, apply-shaped
```

`preview`/`--dry-run` never touch your desktop.

## Apply and roll back

```bash
omni theme apply default --yes      # activate (confirmation on a TTY, --yes for scripts)
omni theme current --json           # what the engine considers active
omni status --json                  # full runtime snapshot
omni theme rollback --yes           # revert to the previous generation
```

Every mutating command (`theme apply`, `theme rollback`,
`wallpaper set`) requires `--yes` when stdin is not a TTY, and refuses
with exit code 2 otherwise. See [CLI.md](CLI.md) for all commands,
flags and exit codes.

## What applying does to your desktop

* Writes **one** owned artifact:
  `~/.local/share/color-schemes/OmniTheme.colors`.
* Applies it with `plasma-apply-colorscheme` — KDE itself copies the
  values into `kdeglobals` and repaints running apps.
* Applies the theme's wallpaper (if declared) via
  `plasma-apply-wallpaperimage`, from a content-hash cache copy.
* Runs the GTK/VS Code/Konsole adapters when those surfaces are
  detected; unsupported surfaces are skipped and reported, never fatal.

What it does **not** touch: Plasma Style, Global Theme, window
decorations, `kdeglobals` by hand, panels/layout. See
[GTK.md](GTK.md) for GTK specifics and
[`../architecture/qt-kde-boundary.md`](../architecture/qt-kde-boundary.md)
for the full boundary.

## Where state lives

```
~/.config/omni-theme/        your overlays + templates (versionable)
~/.local/state/omni-theme/   generations, current/previous, state.json
```

Rollback semantics: [ROLLBACK.md](ROLLBACK.md). Customizing without
touching the repo: [OVERRIDES.md](OVERRIDES.md). Problems:
[TROUBLESHOOTING.md](TROUBLESHOOTING.md).
