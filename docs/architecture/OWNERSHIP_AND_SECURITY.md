# Ownership and Security

Two distinct concerns: **who owns which file** (so user data is never
clobbered and rollback is exact), and **what theme data can and cannot
do** (so themes stay data, never code). The ownership *policy* is normative
in `raw/00_PROJECT_MANIFEST.json` (`ownership_policy`); this document
explains the implementation.

## File ownership model

The engine owns **only what it generated or promoted**. Everything else is
user state and is never silently modified.

| Artifact | Owner |
|---|---|
| `~/.local/share/color-schemes/OmniTheme.colors` | **Omni** (declared in `templates/targets.toml`) |
| `<state>/adapters/wallpaper-cache/`, journals (`kde.json`, `vscode.json`, `konsole.json`, gtk journal), gtk backup snapshots | **Omni** |
| VS Code `workbench.colorCustomizations` managed keys | **Omni** (key-scoped; rest of the file byte-preserved) |
| Konsole `OmniTheme.colorscheme` + the default profile's `[Appearance] ColorScheme=` key | **Omni** (value-scoped; profile otherwise byte-preserved) |
| `~/.config/kdeglobals`, `appletsrc`, GTK `colors.css` (kde-sync), wallpapers, profiles | **KDE / user** — read-only to Omni |

Ownership records live in `state.json` (`managed_targets`: path → sha256 of
the last-written bytes). Conflict inspection compares live bytes against
*those* hashes — so re-theming your own output is safe, while a hand-edited
managed target is a **conflict**: reported, never overwritten without an
explicit `--force` (each forced overwrite is a warning). A file the engine
has no record of is treated as user property and reported as a conflict.

## Write path policy (Session 08)

`core/filesystem.py` enforces, inside `atomic_write` and at every non-atomic
managed write site (adapter journals, backup snapshot/restore, wallpaper
cache copy):

1. **Approved roots** — the XDG-derived base directories
   (`$XDG_CONFIG_HOME`, `$XDG_DATA_HOME`, `$XDG_STATE_HOME`, each defaulted
   to `~/.config`, `~/.local/share`, `~/.local/state`) form the write
   allowlist. No root is as broad as `$HOME`.
2. **Canonicalization + symlink resolution** before validation; relative
   traversal (`..`), absolute escapes, sibling-prefix confusion
   (`~/X-evil` vs `~/X`) and symlink escapes (any component resolving
   outside the root) are rejected.
3. **Ownership policy** (from the control-plane manifest, applied after
   canonicalization; no repair — the engine rejects, never chown/chmods):
   * owner must be the current user (rejects root-owned input);
   * reject group-writable and world-writable files/directories;
   * reject setuid/setgid bits;
   * every parent directory up to the approved root must not be
     world-writable unless sticky.
4. **Atomic replacement** — sibling temp file → flush → fsync → explicit
   mode (or preserve the existing file's mode, so user `chmod 600`
   survives re-theming) → `os.replace`. Failures remove the temp file and
   leave the destination untouched.

Violations raise `PathPolicyError` (`core/errors.py`) and surface as a
controlled CLI failure — no traceback for expected errors.

## Theme data is data, not code

* **Templates are inert.** Rendering is pure substitution over a closed
  helper set (`{{ key }}`, `_strip`, `_rgb`, `mix`, `kde_gradient`); there
  is no escape into code. Rendering is strict — unknown variables,
  malformed helpers and unclosed `{{` fail loudly with file, line and the
  offending expression.
* **No theme-supplied executable runs.** Hooks would live only in the
  repo `hooks/` directory (currently empty); nothing from a theme
  directory is ever executed.
* **Subprocess hygiene.** External commands run as argument arrays; no
  `shell=True` anywhere (audited by tests).
* **Targets are declared, never inferred.** A rendered artifact reaches
  disk only if `templates/targets.toml` declares that exact destination;
  the registry schema is validated strictly (no `..`, no relative
  destinations, duplicates are errors).

### Honest status: third-party theme provenance filtering

`docs/research/ARCHITECTURE_DECISIONS.md` records the intended provenance
model for *installed* third-party themes (denylist of executable-content
files, symlink stripping at any depth, dropped files named on stderr).
**This filtering is not implemented yet** — there is currently no theme
installer; users add themes by hand into `themes/<name>/` or via
`--root`. Hand-added themes are treated with the same trust as shipped
ones: they are parsed as data (and cannot execute anything), but their
values flow into generated files unfiltered. The provenance filter lands
with the installer work and must arrive with tests enforcing it, as
documented in the research notes. Do not treat the intent as shipped.

## What Omni never does

* never writes `kdeglobals`, `QtProject.conf`, `kwinrc`, or any Plasma
  Style / Global Theme package (see [qt-kde-boundary.md](qt-kde-boundary.md));
* never invokes global-theme switching tools that reset layout-adjacent state;
* never modifies, deletes or repairs user files outside its ownership records;
* never weakens or bypasses the checks above to make a command succeed
  (control-plane invariant; also enforced by the test suite).
