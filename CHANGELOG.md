# Changelog

All notable changes to omni-theme-cachy are documented here, by capability.
Sessions 8–18 are the post-Session-7 security and agent-integration arc that
culminates in the first stable release.

## [Unreleased]

### Added

- **Wallpaper→palette extraction** (`core/wallpaper_extractor.py`): a
  dependency-free extractor that turns any wallpaper into a complete 44-role
  omni palette. Deterministic pure-Python k-means with calm-surface
  background selection, hue-coherent accent/status/terminal derivation and
  WCAG contrast floors; images decode through Pillow when available and
  otherwise through a built-in stdlib PNG decoder (8-bit, non-interlaced).
- **`omni theme create`**: generate a theme directory from a wallpaper's
  extracted palette (`--from-wallpaper`, `--name`, `--mode`, `--apply`),
  backed by `core/theme_factory.py` (also used by the GUI). Registered in
  the mutating command inventory with `--yes`/`--json`.
- **plasma-chrome adapter**: theme-driven shell chrome — panel opacity
  (`[panel]`, appletsrc `[PlasmaViews][Panel <id>][Defaults]`), window
  decoration selection (`[kwin]`, kwinrc `[org.kde.kdecoration2]`) and
  tooltip colors (`[tooltips]`, kdeglobals `[Colors:Tooltip]`). All edits
  are key-level, byte-preserving and journalled via `core/kde_config` for
  exact rollback; the session-13 kwinrc guard tests were amended to allow
  this single sanctioned seam (user-directed scope decision) while whole-file
  kwinrc ownership stays forbidden.
- **Omni Theme Settings GUI** (`gui/omni-settings-gui.py`): native Qt
  settings app driving the engine directly — theme apply/rollback, live
  wallpaper→palette preview, per-role color editor saving real theme
  directories, in-app wallpaper watcher, plus a `omni-wallpaper-daemon`
  auto-theming daemon, desktop launcher and systemd user unit.

## [0.1.0] — 2026-08-30

First stable release of the security-hardened theme engine with agent
integration. Primary platform: CachyOS with KDE Plasma 6.

### Security

- **Path policy** (Session 8): single `approved_roots()` allowlist derived from
  the XDG base directories; every write destination is canonicalized, resolved
  and containment-checked inside `atomic_write`; ownership policy (owner,
  group/world write, setuid/setgid, parent-directory world-writability)
  enforced with no repair — the engine rejects and reports, never chowns.
- **Write-site closure** (Session 12): every external write routes through the
  central validator; validate-to-replace TOCTOU window closed by re-validating
  immediately before `os.replace`; snapshot/restore and wallpaper-cache copies
  moved to a validated, atomic `atomic_copy`.
- **KConfig safety** (Session 13): `core/kde_config.py` is the single home for
  KDE INI operations — byte-precise, section-safe, suffix-preserving key
  editing; `configparser` deliberately rejected; `kwinrc`/`plasmarc` pinned
  out of scope by guard tests.
- **Package-manager hygiene** (Session 16): mechanical scans confirm no code
  path invokes a package manager, references KWin/tiling, or can change window
  behaviour; `kwinrc` stays out of scope.

### Activation and rollback

- Immutable generation snapshots with atomic `current`/`previous` symlink
  swaps; failed activations roll themselves back; rollback re-materializes
  engine-owned files byte-exact (sha256-verified) from the previous
  generation's manifest (Sessions 8–9, hardened through 12).
- Deterministic CLI failure contract: rollback without a previous generation
  refuses with an explanatory error (exit 14), never silently (Session 14).

### KDE adapter

- Color scheme application via `plasma-apply-colorscheme` with `kreadconfig6`
  verification; wallpaper via `plasma-apply-wallpaperimage` with journal-based
  pre-Omni restore target; Konsole profile editing through the central
  KConfig layer with byte-exact profile backups (Sessions 9, 11, 13).
- Live-verified on CachyOS Plasma 6.7.4 (Wayland), including apply→verify and
  rollback-refusal contracts (Sessions 9, 11, 18).

### GTK synchronization

- Per-machine capability classification (`GTKCapability`): `kde-native-sync`,
  opt-in `direct`, or `unsupported` with a documented reason (Session 11).
- KDE sync race fixed with a bounded propagation verification window
  (default 2 s, injectable); non-Breeze GTK themes are reported as a boundary,
  never overridden (Session 11).

### Application adapters

- Konsole: profile `[Appearance] ColorScheme=` managed via journals and
  byte-exact backups; generated scheme fully owned.
- VS Code: key-scoped `workbench.colorCustomizations` management with
  journal-backed semantic restore (pre-image hash journaled).
- Both live-verified on Plasma 6.7.4 (Session 18).

### CLI

- Full JSON surface with `schema_version: 1` on every machine-readable
  command (`theme list/current/validate/preview/apply/rollback`, `wallpaper`,
  `status`, `doctor`, `version`, `commands`); failure documents carry
  `{ok: false, errors, warnings}` (Session 14).
- `omni commands --json` inventory derived from the live argparse parser so
  metadata cannot drift; the only hand-maintained part is
  `MUTATING_COMMANDS` (Session 14).
- `--yes` on the three mutating commands only: TTY-confirm, non-TTY-refuse;
  deterministic exit codes (2 refuse, 14 rollback failure).

### Installer

- `install.sh`: checkout or managed clone → dedicated venv → `pip install .`
  → `~/.local/bin` shims for `omni`/`omni-theme`; no sudo, no system Python
  mutation; `requires-python` (>= 3.11) enforced before venv creation;
  idempotent re-run; refuses on local changes (Session 15).
- GitHub Actions smoke test (`install-smoke-test.yml`, archlinux container)
  installing the commit under test via `OMNI_SOURCE_DIR` (Session 15).

### Agent ergonomics / OpenCode integration

- `opencode.json` with conservative permissions: read-only omni commands and
  audit/test commands allowed without prompting; desktop mutation, `git push`
  and `git tag` require asking; package installs, sudo, curl/wget denied
  (Session 17).
- Five project commands in `.opencode/commands/` (`/omni-check`,
  `/omni-preview`, `/omni-apply`, `/omni-security`, `/omni-release-check`)
  wrapping the Omni CLI only; `/omni-apply` requires a clean dry-run before
  `--yes` (Session 17).
- Command mapping documented in `docs/user/OPENCODE.md`; commands discovered
  at runtime by `opencode debug config` (verified against OpenCode 1.18.23,
  Session 18).

### Omarchy reconciliation

- Divergence from Omarchy documented with verified upstream provenance:
  Omni reuses the semantic `colors.toml`/`surfaces.toml` model but ships no
  Hyprland, Quickshell, QML shell, or `shell.json` concepts (Session 10).
- Mechanical divergence audit (`scripts/audit_omarchy_divergence.py`) keeps
  Hyprland/Quickshell literals out of engine code.

### Path safety

- `scripts/audit_write_paths.py` AST review aid enumerates every candidate
  write site (36) for manual review against the central policy inventory in
  `docs/architecture/OWNERSHIP_AND_SECURITY.md` (Session 12).

### Final verification (Session 18)

- Integrated release gate: audits, full test suite (782 passed, 1 skipped by
  design), compileall, CLI acceptance, installer smoke test in a clean
  temporary HOME, OpenCode integration checks, claim audit, and a live-KDE
  apply/verify/restore cycle on Plasma 6.7.4 (Wayland). See
  `docs/RELEASE_VERIFICATION.md`.
