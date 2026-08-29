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

### Session 12 hardening

* **Re-validation before replacement.** `atomic_write` (and every helper
  built on it) re-runs `validate_write_target` immediately before
  `os.replace`, closing the validation→replacement race: a path
  component that turns into a symlink after the initial check is
  rejected, never followed (tested by simulated-race tests in
  `tests/security/test_symlink_escape.py`).
* **`atomic_copy`.** File copies (backup snapshots, restores, wallpaper
  cache repair) now go through a central atomic, policy-validated copy
  primitive instead of raw `shutil.copyfile` — a rejected or failed copy
  can never truncate the destination.

### Session 13 hardening: KDE INI writes are section-safe

KConfig files are not generic INI: keys carry bracket suffixes
(`key[$e]`, `key[$i]`, locale tags), the same group may appear more than
once (later assignments win), and formatting is user-visible state.
`configparser` is therefore **not used anywhere**: it lowercases keys,
rejects duplicate sections and would re-serialise whole files.

* **`core/kde_config.py`** is the single home for KDE INI operations:
  `parse_ini` (verbatim keys, last-wins, suffix variants distinct),
  `set_ini_key` (byte-precise; never creates a duplicate section;
  rewrites the winning occurrence in place, preserving any key suffix;
  appends into the last existing section block or at end-of-file) and
  `remove_ini_key` (removes every variant of the managed key, keeps the
  header). Konsole profile surgery, `konsolerc` detection parsing and
  the gtk sync `kdeglobals` parser all delegate to it.
* **Mechanism per KDE INI file** (audited in session 13):
  * `kdeglobals` — never written by Omni; written by KDE's own
    `plasma-apply-colorscheme` and read back via `kreadconfig6` (native
    tooling kept);
  * `kwinrc`, `plasmarc` — never touched by any code path (pinned by
    `tests/unit/test_kwin_config.py`);
  * `konsolerc` — read-only (detection parses it; never written);
  * Konsole `*.profile` — value-scoped edit of `[Appearance]
    ColorScheme=` via `core/kde_config.set_ini_key`; a byte snapshot in
    the konsole journal provides exact rollback;
  * `OmniTheme.colors` / `OmniTheme.colorscheme` — Omni-owned generated
    artifacts written whole via the validated atomic write path.
* Every resulting write still goes through `atomic_write_text` — the
  central `kde_config` functions only transform text; persistence and
  policy enforcement remain with `core/filesystem.py`.

### Session 16 hardening: scope hygiene (packages, KWin, window behaviour)

Two mechanical scans over `core/`, `adapters/`, `hooks/`, `scripts/`
re-verified the product boundary (session 16; findings below are the
reviewed result):

* **Package managers.** Pattern scan for `pacman -S`, `yay`, `paru`,
  `dnf/apt/zypper install`, `flatpak/snap install`, `os.system`,
  `os.popen` and `subprocess` with `shell=True`: **zero matches**. The
  engine never installs packages, AUR helpers included.
  `install.sh` (exempt from the code scan, checked anyway) contains no
  package-manager calls — it only provisions a dedicated venv and
  `pip install .` into it. The CI workflow installs `git python` via
  pacman inside its own throwaway archlinux container; that is CI
  environment provisioning, not engine code and not a runtime path.
* **KWin / tiling references.** Scan for `kwin`, `tiling`, `krohnkite`,
  `kzones`, `polonium`, `plasmazones`, `BorderlessMaximizedWindows`:
  **zero matches in code** (`core/`, `adapters/`, `hooks/`,
  `scripts/`). Every hit lives in `docs/` and classifies as:
  * *theme-related scope statements* — this document, the user-facing
    `OPTIONAL_KWIN_SCRIPTS.md`, `ADAPTERS.md` ("kwinrc and panels are
    separate surfaces"), `DIVERGENCE_FROM_OMARCHY.md`;
  * *research snapshots* — `docs/research/` notes describing what
    Omarchy/KDE do (not what Omni does);
  * *legacy/unintended*: none found. Nothing to remove; the session 13
    guard tests (`tests/unit/test_kwin_config.py`) remain the pin and
    were not duplicated or weakened.
* **Window behaviour.** `BorderlessMaximizedWindows` (or any equivalent
  maximized-window decoration toggle) does not exist in the code,
  templates or themes. No opt-in surface is needed; if one is ever
  added it must go through `core/kde_config.py`, be opt-in, reversible
  and documented — see the user doc's "Window behaviour settings".

Consequence for the activation flow: a normal `omni theme apply
default --yes` cannot install packages, enable KWin scripts, change
tiling behaviour, or replace KWin — there is no code path that could.

## Write-site inventory (Session 12)

Every filesystem write site in `core/`, `adapters/`, `hooks/` and
`scripts/`, and how each satisfies the exit condition: centrally guarded,
inside controlled engine-private directories, or explicitly documented as
a dev-asset/native operation. `scripts/audit_write_paths.py` lists the
candidate sites mechanically (reviewer assistance only — an AST hit
proves nothing by itself); this table is the reviewed result.

| Site | Operation | Target source | Expected root | Guard | Ownership | Test |
|---|---|---|---|---|---|---|
| `core/staging.py` staged artifacts + `manifest.json` | `atomic_write` | registry targets → `<state>/staging` | `$XDG_STATE_HOME` | validator inside `atomic_write` | validator (uid/bits) | `test_write_coverage.py` |
| `core/activation.py` `_materialize_targets` | `atomic_write` | declared targets → config/data homes | XDG base dirs | validator + conflict gate | validator | `test_write_coverage.py`, `test_failure_rollback.py` |
| `core/state.py` `write_state` | `atomic_write_text` | engine state root | `$XDG_STATE_HOME` | validator | validator | unit state tests |
| `core/state.py` `switch_link` / `promote_generation` | `os.symlink` + `os.replace` in state root | generation id (regex-checked, no `..`) | state root | `_checked_gen_id`; refuses non-symlink link names | engine-owned | `test_failure_rollback.py` |
| `core/activation.py` rollback unlink of engine-created files | `unlink` | only files this attempt created (absent from prior owned map) | XDG base dirs | creation provenance check | engine-owned | `test_failure_rollback.py` |
| `core/activation.py` dry-run sandbox | `mkdtemp` + `rmtree` | engine state root | state root | engine-created, removed after run | engine-owned | CLI tests |
| `core/filesystem.py` `atomic_write` / `atomic_copy` | mkstemp sibling → fsync → chmod → re-validate → `os.replace` | caller-provided | XDG base dirs | the policy itself | validator | `test_atomic_write.py`, `test_symlink_escape.py` |
| `adapters/support.py` `snapshot_file` | `atomic_copy` → `<state>/adapters/<name>-backups/` | live target bytes | state root | validator via `atomic_copy`; first snapshot never overwritten | engine-owned backup | `test_write_path_coverage.py` |
| `adapters/support.py` `restore_snapshot` | `atomic_copy` backup → live target | journalled backup path | XDG base dirs | validator via `atomic_copy`; violation → warning, file untouched | engine-owned restore | `test_write_path_coverage.py` (incl. outside-root refusal) |
| `adapters/kde/wallpaper.py` `ensure_cached` | `atomic_copy` → `<state>/adapters/wallpaper-cache/` | theme wallpaper (format-sniffed first) | state root | validator via `atomic_copy` | engine-owned cache | `test_write_path_coverage.py` |
| adapter journals (`kde.json`, `vscode.json`, `konsole.json`, `gtk.json`) | `atomic_write_text` | engine state root | `$XDG_STATE_HOME` | validator | engine-owned | `test_write_path_coverage.py` |
| `adapters/vscode` apply/rollback | `atomic_write_text` | discovered `<config>/Code*/User/settings.json` | `$XDG_CONFIG_HOME` | validator | key-scoped: only managed keys; rest byte-preserved | `test_write_path_coverage.py` + vscode unit tests |
| `adapters/konsole` apply/rollback | `atomic_write_text` | scheme + default profile under `$XDG_DATA_HOME/konsole` | `$XDG_DATA_HOME` | validator + `assert_within` traversal guard | value-scoped profile key edited via `core/kde_config` (section-safe, suffix-preserving); scheme fully owned | konsole unit tests + `test_kde_config.py` |
| `adapters/gtk/direct.py` apply | `atomic_write_text` | `~/.config/gtk-{3,4}.0/gtk.css` | `$XDG_CONFIG_HOME` | validator + marker-owned block; opt-in only | marker-scoped block | gtk unit tests |
| KDE `OmniTheme.colors` | `atomic_write` (core-managed target) | declared in `templates/targets.toml` | `$XDG_DATA_HOME/color-schemes` | validator + managed-target conflict gate | Omni-owned generated artifact | KDE adapter tests |
| `scripts/generate_default_wallpaper.py` | `open("wb")` into `themes/default/wallpapers/` | repo asset tree | repository checkout (dev tooling, never runtime, never user config) | documented dev-asset exception | repo asset | `audit_write_paths.py` lists it for review |
| native desktop operations | `plasma-apply-*`, `kreadconfig6` via argument-array subprocess | desktop state | KDE's own contract | out of the engine's filesystem scope; Omni writes no files here | KDE/user | subprocess-hygiene tests |

`hooks/` contains no Python write sites (bash reload scripts only).

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
