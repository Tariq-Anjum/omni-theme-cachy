# Session 18 — Final Verification, Release Readiness, Changelog, and Tagging

> Read `raw/00_AGENT_EXECUTION_CONTRACT.md` and `raw/00_PROJECT_MANIFEST.json` first — each exactly once. If output appears truncated, do NOT re-read; proceed with what you have or report BLOCKED naming the exact problem.

## Objective

Close the post-Session-09 work only after the entire repository passes one integrated audit. Do not tag or push a release merely because the command sequence completed.

## Resolved facts — read before implementing

The user has decided the release tag: **`v0.1.0`**. Do not propose a different version. This is the first stable release of the security-hardened theme engine with agent integration.

## OpenCode tools

Use: `read`, `glob`, `grep`, `bash`, `edit`, `write`, `lsp`, `websearch`/`webfetch` for any remaining current platform claim.
Free/open-source tools: `rg`, `fd`, `jq`, `python`, `pytest`, `git`.

## Step 1 — Clean state

    git status --short
    git diff --check

If unrelated changes exist, stop and report them. Do not delete user work.

## Step 2 — Audit scripts

Run:

    python scripts/audit_omarchy_divergence.py
    python scripts/audit_write_paths.py

Expected:
- no unintended Hyprland/Quickshell leakage
- all candidate write paths reviewed

## Step 3 — Test suite

Run:

    pytest -q
    python -m compileall core adapters hooks scripts

If configured:

    ruff check .
    mypy .

Do not introduce new linters at release time unless already part of project policy.

## Step 4 — CLI acceptance

Run:

    omni version
    omni commands --json | jq .
    omni theme list
    omni theme validate default
    omni theme preview default --json | jq .
    omni doctor --json | jq .
    omni status --json | jq .
    omni theme apply default --dry-run --yes --json | jq .

Verify:
- no live desktop changes
- no current symlink change
- no external configuration mutation
- no unresolved conflict

## Step 5 — Real-KDE verification (requires a live KDE session)

Only if the current environment is the target KDE Plasma 6 workstation:

    omni theme apply default --yes --json | jq .

Then verify:
- KDE Color Scheme
- wallpaper
- application adapters
- adapter status
- generated targets

Then:

    omni status --json | jq .
    omni theme current --json | jq .

Then:

    omni theme rollback --yes --json | jq .

Verify the previous state is actually restored.

Do not claim GTK persistence unless the relevant KDE session lifecycle has been tested.

No-KDE fallback: if no live KDE session is available, mark all real-KDE claims as "not verified" and proceed with the rest of the gate. Do not wait or retry.

## Step 6 — Installer verification

Use a temporary HOME where practical:

    tmp_home="$(mktemp -d)"
    HOME="$tmp_home" bash install.sh
    HOME="$tmp_home" \
      PATH="$tmp_home/.local/bin:$PATH" \
      omni version
    HOME="$tmp_home" \
      PATH="$tmp_home/.local/bin:$PATH" \
      omni theme list
    HOME="$tmp_home" \
      PATH="$tmp_home/.local/bin:$PATH" \
      omni commands --json

Clean up temporary test artifacts.

## Step 7 — OpenCode integration verification

Verify:
- `opencode.json` exists and parses
- `.opencode/commands/` contains the five commands
- `docs/user/OPENCODE.md` exists and references the commands
- `tests/test_opencode_integration.py` passes

If `opencode` is installed, verify the commands are discoverable. If not, verify file structure only and record runtime verification as "not verified."

## Step 8 — Claim audit

Search for unsupported claims:

    rg -n "supported|works|complete|universal|always|guaranteed|Hyprland|Quickshell|GTK" README.md docs

Review every positive claim. Change:
- "supports GTK" to a capability-specific claim where necessary
- "works on KDE" to an observed/tested claim

## Step 9 — Changelog

Create/update: `CHANGELOG.md`

Document Sessions 8–18 by capability, not merely by commit. Include:
- activation/rollback
- KDE adapter
- application adapters
- CLI
- security
- Omarchy reconciliation
- GTK synchronization
- path safety
- KDE config safety
- agent ergonomics
- installer
- OpenCode integration
- final verification

## Step 10 — Tag decision

Only propose a tag if:
- all critical tests pass
- no unresolved security issue
- no known data-loss issue
- real KDE validation is documented or clearly marked unverified
- installer works
- CLI JSON works
- OpenCode commands load
- git tree is clean

If anything fails:
- do not tag
- do not push
- report exact blocker

The user has decided the tag is `v0.1.0`. Do not propose a different version.

## Step 11 — Release commit and tag

Only after the above passes:

    git add CHANGELOG.md README.md docs .opencode opencode.json scripts tests core adapters hooks
    git commit -m "release: v0.1.0 — security-hardened theme engine with agent integration"
    git tag -a v0.1.0 -m "omni-theme-cachy v0.1.0"

Before pushing:

    git status --short
    git log --oneline --decorate -10
    git show --stat --oneline HEAD

Then:

    git push origin main
    git push origin v0.1.0

Do not use force push.

## Step 12 — Release verification doc

Create: `docs/RELEASE_VERIFICATION.md` with:

1. Implemented features
2. Architecture changes
3. KDE tests actually performed
4. GTK behavior actually verified
5. Application adapters verified
6. Security tests
7. Installer result
8. OpenCode integration result
9. Known limitations
10. Git commits
11. Release tag
12. Exact unverified items

## Exit condition

The project is release-ready only when the report distinguishes:
- implemented
- tested
- verified on real KDE
- supported but unverified
- unsupported
- known issue

Never collapse those into one "complete" label.

## STOP / BLOCKED

Report BLOCKED and do not guess if:
- Any critical test fails and cannot be isolated.
- A security audit finds real leakage that cannot be cleanly resolved.
- The installer fails in a clean environment.
- The control plane and the code conflict and no higher-authority rule resolves it.

Do not invent a workaround silently.

## Completion

On PASS:
1. Update `raw/00_PROJECT_MANIFEST.json`:
   - set `current_baseline` to "Session 18 completed"
   - set `status` to "RELEASE_v0.1.0_TAGGED"
   - set `next_sessions` to `[]` (empty — all sessions complete)
   - add a `session_18` record with the verification summary and tag
2. Update the README control-plane baseline line to Session 18 and the release tag.
3. Commit the verification doc:

       git add docs/RELEASE_VERIFICATION.md raw/00_PROJECT_MANIFEST.json README.md
       git commit -m "docs: record final verification and release readiness"

4. Push:

       git push origin main

Do not force push.

## Commit

The release commit (Step 11) and the verification-doc commit (Completion step 3) are separate. Do not combine them.
