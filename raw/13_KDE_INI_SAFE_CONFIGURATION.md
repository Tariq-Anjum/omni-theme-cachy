# Session 13 — KDE INI Configuration Safety and KWin/KDE State Preservation

> Read `raw/00_AGENT_EXECUTION_CONTRACT.md` and `raw/00_PROJECT_MANIFEST.json` first — each exactly once. If output appears truncated, do NOT re-read; proceed with what you have or report BLOCKED naming the exact problem.

## Objective

Eliminate raw string mutation of KDE INI-style configuration. Prevent duplicated sections, malformed files, lost user settings, and unintended corruption.

## Scope

Audit the KDE .rc/.ini files Omni touches:
- kwinrc
- kdeglobals
- konsolerc
- plasmarc
- any other KDE .rc/.ini file Omni writes

Do not rewrite files that Omni does not actually own.

## OpenCode tools

Use: read, glob, grep, bash, edit, write, websearch, webfetch.
Free/open-source utilities: rg, fd, python, pytest, git.

## Step 1 — Audit

    rg -n "\[[A-Za-z0-9_:-]+\]|write_text|open\(|kwriteconfig|kreadconfig|configparser" core adapters hooks
    rg -n "kwinrc|kdeglobals|konsolerc|plasmarc" core adapters hooks

Classify every write site: file, mechanism, ownership, guard, test. Where a native tool is already used (for example `plasma-apply-colorscheme` for the color scheme), keep it — do not replace working native tooling with hand-rolled file writes.

## Step 2 — Choose the mechanism per file

Do not assume Python `configparser` is always the best option. Preferred order:
1. KDE-native configuration CLI/API (`kwriteconfig6`/`kreadconfig6`, `plasma-apply-colorscheme`) if installed and documented.
2. A dedicated parser that understands the file format.
3. `configparser` only when the file is genuinely compatible with its semantics.

KDE config files can carry semantics a generic INI parser does not preserve: key suffixes such as `key[$e]` (immutable/locale flags), inline comments, and section ordering. If you use `configparser`, set `optionxform = str` and prove in tests that unmanaged content survives a round-trip.

## Step 3 — Centralize safe INI operations

If repeated safe INI operations exist, create `core/kde_config.py`. Every direct file write must route through Session 8/12's validated atomic write path in `core/filesystem.py`. Do not hand-roll `tmp.open(...)` + `tmp.replace(...)` — that bypasses `validate_write_target`, the ownership policy, fsync, and permission preservation.

## Step 4 — KWin

If code modifies a KWin setting, create a dedicated function such as `set_kwin_setting(...)`. It must:
- read existing state;
- modify only the requested key;
- preserve unrelated keys;
- avoid duplicate sections;
- write atomically through the validated write path;
- participate in ownership/hash tracking;
- have rollback.

Do not trigger a KWin reconfigure or restart during tests. Tests use tmp fixtures only; the real `~/.config/kwinrc` must never be touched by tests.

## Step 5 — Tests

Create:
- tests/unit/test_kde_config.py
- tests/unit/test_kwin_config.py

Test, using tmp_path fixtures only (never the real user config):
- existing section
- missing section
- existing unrelated keys
- existing target key
- repeated application (idempotency)
- rollback
- format stability where required
- no duplicate section
- keys with `[$e]`-style suffixes survive, where the target file uses them

Example:

    def test_does_not_duplicate_windows_section(tmp_path):
        ...

## Step 6 — Verify ownership and scope

If a setting is not necessary for the theme engine's core purpose, do not modify it merely to create a "seamless" experience. The engine must avoid silently changing:
- window behavior
- tiling behavior
- KWin scripts
- global workflow preferences

unless explicitly part of the product scope.

## Step 7 — Optional helper fallback

Where possible use:

    kreadconfig6 ...
    kwriteconfig6 ...

only if actually installed. Never fail just because one optional helper binary is absent — fall back to the next mechanism in Step 2's preferred order and report which path was used.

## Step 8 — Run

    pytest -q
    python -m compileall core adapters
    git diff --check

## Exit condition

No code path that writes KDE INI-like configuration uses naive section appending. All direct file writes route through the validated atomic write path or a KDE-native tool.

## STOP / BLOCKED

Report BLOCKED and do not guess if:
- A write site cannot be made section-safe without redesigning an earlier session's public contract.
- A target file uses KDE-specific semantics that no available mechanism preserves, and you cannot determine which mechanism is safe.
- Making a write safe would require bypassing Session 8's path or ownership validation.
- The control plane and the code conflict and no higher-authority rule resolves it.

Do not invent a workaround silently.

## Completion

On PASS:
1. Update `raw/00_PROJECT_MANIFEST.json`: set `current_baseline` to "Session 13 completed", update `status`, remove `13` from `next_sessions`.
2. Update the README control-plane baseline line to Session 13.
3. Commit per AGENTS.md, then `git pull --rebase origin main`, then push.

## Commit

    git add core adapters tests docs raw/00_PROJECT_MANIFEST.json README.md
    git commit -m "fix: make KDE configuration writes section-safe and atomic"
