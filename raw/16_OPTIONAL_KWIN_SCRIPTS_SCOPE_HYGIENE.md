# Session 16 — KWin Scope Hygiene

> Read `raw/00_AGENT_EXECUTION_CONTRACT.md` and `raw/00_PROJECT_MANIFEST.json` first — each exactly once. If output appears truncated, do NOT re-read; proceed with what you have or report BLOCKED naming the exact problem.

## Objective

Keep window-management and tiling behavior explicitly outside the core theme engine. Omni targets KDE Plasma 6, KWin's traditional floating-window workflow, and mouse-driven desktop usage. It must not silently install or enable third-party AUR/Pacman packages, KWin scripts, or tiling extensions.

"Optional" here means: community tiling scripts (Krohnkite, Kzones, Polonium, PlasmaZones) and similar window-management extensions are out of scope for the theme engine. This session verifies and documents that boundary — it does not implement or ship them.

## OpenCode tools

Use: read, glob, grep, bash, edit, write, websearch, webfetch.
Free/open-source utilities: rg, fd, git, python, pytest.

## Step 1 — Package-installer scan

Scan code paths that would *execute* package managers. Exempt `install.sh` and `docs/` documentation (which may legitimately describe how users install prerequisites).

    rg -n --glob '*.py' \
      "pacman -S|yay -S|paru -S|dnf install|apt install|zypper install|flatpak install|snap install|os\.system|os\.popen|subprocess\..*shell=True" \
      core adapters hooks scripts

Expected: no automatic AUR/system package installation in code. Document the finding in the hygiene report. If `install.sh` contains prerequisite documentation, that is acceptable and not a violation.

## Step 2 — KWin scope scan

    rg -n "kwin|tiling|krohnkite|kzones|polonium|plasmazones|BorderlessMaximizedWindows" core adapters hooks scripts docs

Classify each reference:
- theme-related (legitimate scope)
- optional behavior (must be isolated and not activated by default)
- legacy (from an earlier session, to be removed)
- unintended (remove from core)

Remove unintended tiling/window-management behavior from the core.

Session 13 already established KWin scripts as out of scope for the theme engine and added `tests/unit/test_kwin_config.py` with kwinrc write-scope guard tests. Extend the guards if this session finds new KWin-touching code; do not duplicate the existing tests.

## Step 3 — Reconcile the optional KWin scripts doc

Read the existing `docs/user/OPTIONAL_KWIN_SCRIPTS.md` (created in Session 9) first. Reconcile and update it — do not overwrite Session 9's content wholesale.

Required content:
- Omni Theme Engine does not install or manage window-tiling behavior.
- Community tiling scripts (Krohnkite, Kzones, Polonium, PlasmaZones) are out of scope.
- If documenting community scripts, verify current sources before publication.
- Do not imply endorsement or security review.

Fallback: if web verification of community-script sources fails, use the latest `docs/research/*` snapshot and label unverified claims as "per research snapshot, unverified."

## Step 4 — Borderless behavior

If the project includes a setting such as `BorderlessMaximizedWindows`, ensure it is:
- explicitly opt-in;
- safely parsed (through `core/kde_config.py`);
- reversible;
- documented.

Do not automatically apply window-behavior changes as part of ordinary theme activation.

## Step 5 — Tests

Verify the existing Session 13 kwinrc write-scope guards still hold. Add guard tests only for new KWin-touching code found in Step 2.

Run:

    pytest -q
    pytest -q tests/unit/test_kwin_config.py
    git diff --check

## Exit condition

A normal `omni theme apply default --yes` does not:
- install packages
- enable KWin scripts
- change tiling behavior
- replace KWin

## STOP / BLOCKED

Report BLOCKED and do not guess if:
- The package-installer scan finds automatic AUR/Pacman invocation in code that cannot be removed without breaking a legitimate feature.
- A KWin-touching code path cannot be cleanly isolated from the theme activation flow.
- The existing `docs/user/OPTIONAL_KWIN_SCRIPTS.md` contradicts the session requirements and you cannot determine which is correct.
- The control plane and the code conflict and no higher-authority rule resolves it.

Do not invent a workaround silently.

## Completion

On PASS:
1. Update `raw/00_PROJECT_MANIFEST.json`: set `current_baseline` to "Session 16 completed", update `status`, remove `16` from `next_sessions`.
2. Update the README control-plane baseline line to Session 16.
3. Commit per AGENTS.md, then `git pull --rebase origin main`, then push.

## Commit

    git add docs tests core adapters hooks scripts raw/00_PROJECT_MANIFEST.json README.md
    git commit -m "fix: harden KWin scope hygiene and prevent silent package installation"
