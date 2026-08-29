# Release Verification — v0.1.0

Verification record for the first stable release. Labels are used exactly as
defined by the session-18 exit condition and never collapsed:

- **implemented** — code exists and is exercised by the suite
- **tested** — covered by automated tests in this repository
- **verified on real KDE** — executed against the live CachyOS Plasma 6
  workstation during this gate
- **supported but unverified** — designed and shipped, no live confirmation
- **unsupported** — explicitly out of scope, with the reason
- **known issue** — documented gap or limitation

Environment observed at verification time: CachyOS, kernel
7.2.0-rc7-1-cachyos-rc, KDE Plasma 6.7.4, Wayland session, Python 3.14.7,
OpenCode 1.18.23.

## 1. Implemented features

- Semantic palette (`colors.toml`) rendered through templates into per-app
  configuration — implemented.
- Staging, atomic generation activation, user overrides, rollback —
  implemented.
- Adapters: KDE colorscheme + wallpaper, Konsole, VS Code, GTK — implemented.
- Security model: approved-roots path policy, ownership policy, atomic
  writes, KConfig layer — implemented.
- CLI with `--json`/`--yes`/`--dry-run` and `omni commands --json`
  inventory — implemented.
- `install.sh` installer + GitHub Actions smoke test — implemented.
- OpenCode integration (`opencode.json`, five `.opencode/commands/`,
  `docs/user/OPENCODE.md`) — implemented.

## 2. Architecture changes across Sessions 8–18

- Single write validator inside `atomic_write` + `atomic_copy` for all
  non-atomic managed copies (S8, S12).
- `core/kde_config.py` as the only KDE INI editor: parse/set/remove with
  byte precision; `configparser` rejected (S13).
- GTK capability classification (`adapters/gtk/capability.py`) with bounded,
  injectable propagation-verify window (S11).
- JSON failure documents and parser-derived command inventory in
  `core/cli.py`; `MUTATING_COMMANDS` remains the only hand-maintained CLI
  metadata, and the S18 audit confirmed it matches `opencode.json` bash
  rules (S14, S18).
- Installer with two source modes and `requires-python` pre-check (S15).
- Divergence audit and write-path audit scripts under `scripts/` (S10, S12).

## 3. KDE tests actually performed (live, this gate)

Real apply on the live Plasma 6.7.4 Wayland desktop
(`omni theme apply default --yes --force --json`):

- Result `VERIFIED`; all four adapters reported applied+verified:
  KDE colorscheme (plasma-apply-colorscheme), wallpaper, VS Code, Konsole.
- `kdeglobals` `ColorScheme=OmniTheme` observed via `kreadconfig6`
  independently of the engine.
- Wallpaper target confirmed via `omni wallpaper current --json`.
- Generated targets confirmed on disk: `OmniTheme.colors`,
  `OmniTheme.colorscheme`.
- `omni status --json`: `current_theme=default`, `managed_targets=1`,
  `consistent=true`; `omni theme current --json` agreed.
- Konsole profile key observed as `ColorScheme=OmniTheme`; GTK
  `colors.css` (gtk-3.0 and gtk-4.0) rewritten identically by the
  kde-gtk-config daemon during the apply — the S11 sync behavior
  reproduced.
- One conflict guard event: a leftover engine-generated
  `OmniTheme.colors` from earlier sessions' tests was "untracked" relative
  to the fresh state; the apply refused without `--force` and succeeded
  with it. Content verified engine-generated (template header) before
  forcing — **verified on real KDE**.
- Rollback: `omni theme rollback --yes` refused with the documented error
  "no previous generation recorded in state.json; nothing to roll back to"
  (deterministic exit-14 contract from S14). This was a first-ever apply
  over a bare state, so no previous generation existed — **verified on
  real KDE** as the refusal contract; the restore path below was executed
  from the journals instead.
- Restore to pre-session desktop (all byte-exact unless noted):
  - VS Code `settings.json`: reconstructed from the applied shape; sha256
    matches the journal's `file_hash_before` — **verified on real KDE,
    byte-exact**.
  - Konsole `Bash.profile`: restored from the adapter's own backup; sha256
    matches the pre-apply capture — **verified on real KDE, byte-exact**.
  - KDE color scheme: `plasma-apply-colorscheme SweetAmbarBlue` (native op);
    `ColorScheme=SweetAmbarBlue`, widget style `Breeze` re-confirmed.
  - GTK `colors.css`: re-propagated automatically by the kde-gtk-config
    daemon after the scheme restore; sha256 matches the pre-apply capture.
  - Wallpaper: `Image` key restored to the journaled pre-Omni value
    (`WhiteSur/#light`) and the shell refreshed — **verified on real KDE**
    (config value exact; the dynamic-wallpaper schedule state was never
    touched).
  - Engine bookkeeping: state files created by this apply removed so
    `omni status` reports the pre-session condition
    (`state_exists=false`, no current theme).

## 4. GTK behavior actually verified

- `kde-native-sync` mode on the live desktop: daemon-propagated
  `colors.css` observed both on apply and on restore — **verified on real
  KDE**.
- Non-Breeze boundary (`WhiteSur-Light` configured): reported in warnings,
  theme choice left untouched — **verified on real KDE**.
- Cross-login persistence of the sync chain: **supported but unverified**
  (logout would interrupt the agent session; deliberately not tested).
- `direct` CSS mode: **tested** (unit/integration suite), **supported but
  unverified** on a real desktop.

## 5. Application adapters verified

- Konsole: profile edit + generated scheme live-verified; rollback-exact
  backup restore live-verified — **verified on real KDE**.
- VS Code: key-scoped write live-verified; journal hash restore live-verified
  — **verified on real KDE**.
- Adapter capability reporting in `doctor --json`/`preview --json` matches
  the live machine — **verified on real KDE**.

## 6. Security tests

- Full suite: **782 passed, 1 skipped** (the wrong-owner case needs root by
  design). `python -m compileall core adapters hooks scripts` clean.
- `scripts/audit_omarchy_divergence.py`: clean — no Hyprland/Quickshell
  leakage.
- `scripts/audit_write_paths.py`: 36 candidate sites enumerated; all
  accounted for in the reviewed inventory in
  `docs/architecture/OWNERSHIP_AND_SECURITY.md`.
- No ruff/mypy at release time: not configured in project policy, so not
  introduced.

## 7. Installer result

- Clean temporary HOME, `OMNI_SOURCE_DIR` pointing at the release commit:
  install completed without sudo; shims created; `omni version`,
  `omni theme list`, `omni commands --json` all passed from the installed
  shims; temporary HOME removed afterwards — **tested, passing**.
- Managed-clone (end-user) mode and refuse-on-local-changes: verified in
  Session 15; CI workflow provisions the archlinux container run on push —
  **tested previously, supported**.

## 8. OpenCode integration result

- `opencode.json` parses; five commands present in `.opencode/commands/`;
  `docs/user/OPENCODE.md` references them;
  `tests/test_opencode_integration.py` — 26 passed.
- Runtime discovery verified with the installed client:
  `opencode debug config` (1.18.23) lists all five `omni-*` commands from
  the merged project config — **tested and runtime-verified**.
- TUI interactive command execution — **supported but unverified** (not
  exercised in this environment).

## 9. Known limitations

- **GTK**: gtk-4.0-only systems without KDE sync remain **unsupported**
  (libadwaita ignores user CSS); non-Breeze themes keep their own styling
  while colors propagate — documented boundary, not a bug.
- **KWin scripts / tiling / package installs**: **unsupported** by design;
  guard tests pin `kwinrc`/`plasmarc` out of scope.
- **Cross-login persistence**: **supported but unverified** (KDE-owned
  sync chain; logout not exercised).
- **VS Code restore**: journaled pre-image is a hash, so restore is
  semantic by design; this gate's restore was byte-exact because the
  applied shape was fully known — **known issue** (snapshot improvement
  noted since S11).
- **First-apply undo**: rollback requires a previous generation; undoing a
  first-ever apply relies on the adapter journals/backup, as exercised in
  §3 — **known issue**, documented in `docs/user/ROLLBACK.md`.
- **Theme discovery** is cwd-relative by design (documented, not
  redesigned).
- **Third-party theme provenance filtering**: not implemented (no theme
  installer exists) — **unsupported** for now.
- **KDE session lifecycle** (logout/login): **not verified** per the
  logout-safety rule.

## 10. Git commits

- `6415a41` — release: v0.1.0 — security-hardened theme engine with agent
  integration (adds `CHANGELOG.md`, README claim fix)
- Session commits b4c809c (S8) through 0414c4b/2f0abdd (S17) carry the
  feature and verification history; see `raw/00_PROJECT_MANIFEST.json` for
  the per-session records.

## 11. Release tag

- `v0.1.0` — annotated tag on `6415a41`, pushed to `origin`.

## 12. Exact unverified items

1. GTK cross-login persistence (kde-sync chain across logout/login).
2. Direct-GTK mode on a real desktop (suite-tested only).
3. OpenCode TUI interactive execution of the five commands.
4. KDE logout/login lifecycle behavior.
5. CI workflow's first real run on the pushed release commit (workflow
   execution is triggered by the push itself).
