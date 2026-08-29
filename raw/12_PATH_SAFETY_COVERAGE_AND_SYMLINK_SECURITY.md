# Session 12 — Path Safety Coverage and Symlink-Safe Writes

> Read `raw/00_AGENT_EXECUTION_CONTRACT.md` and `raw/00_PROJECT_MANIFEST.json` first — each exactly once. If output appears truncated, do NOT re-read; proceed with what you have or report BLOCKED naming the exact problem.

## Objective

Prove that every filesystem write path is protected by the central filesystem policy. Session 08 implemented the central path/ownership enforcement — `approved_roots`, `validate_write_target`, `PathPolicyError`, and validation inside the atomic write path — plus the initial security tests. This session turns that into measured, complete write-path coverage: verify Session 8's work independently, find what it missed, and close the gaps.

## OpenCode tools

Use: read, glob, grep, bash, edit, write, lsp.
Free/open-source utilities: rg, fd, python, pytest, git.

## Step 1 — Identify the actual security primitive

Read in full:
- core/filesystem.py
- core/staging.py

Session 8 implemented `approved_roots()` (the three XDG base directories), `validate_write_target()` (canonicalize, resolve, containment, sibling-prefix safety, symlink-escape rejection, ownership policy), `PathPolicyError` in core/errors.py, and enforcement inside `atomic_write` plus explicit calls at the non-atomic managed sites. Verify this against the code — do not take this description on faith — and document:
- function name
- signature
- root semantics
- symlink semantics
- exception type

Do not rename working APIs solely to match this prompt.

## Step 2 — Verify and extend the write-site inventory

Search all write sites:

    rg -n --glob '*.py' \
      "write_text|write_bytes|open\(|Path\(|os\.replace|os\.rename|os\.symlink|shutil\.copy|shutil\.copy2|shutil\.copytree" \
      core adapters hooks scripts

Extend this pattern if you discover write primitives it does not cover (for example `os.fdopen`, `Path.touch`, `os.link`).

Session 8 classified write sites and reported all managed writes routing through the validator, with `scripts/generate_default_wallpaper.py` documented as dev asset tooling. Treat that as the starting hypothesis and verify it independently. Finding a site Session 8 missed is this session's primary value. Build a review table:

    file | operation | target source | expected root | guard | ownership | test

## Step 3 — Guard every external target

Every write outside an internally created temporary directory must have:
- trusted root
- validated candidate
- ownership decision
- atomic write strategy

Examples of external targets:
- ~/.local/share/color-schemes
- ~/.config/Code/User
- ~/.local/state/omni-theme
- wallpaper cache
- terminal profile directory
- KDE user data

Route any new guards through Session 8's validated write path. Do not add parallel, caller-local security logic.

## Step 4 — Symlink safety tests

Test, using isolated tmp directories:
- target is symlink to allowed file
- target is symlink to outside root
- parent directory is symlink
- candidate resolves outside root
- broken symlink
- dangling path that later becomes a symlink (TOCTOU)

## Step 5 — Atomic write helper

The project already has the atomic write helpers from Session 8 (`atomic_write`, `atomic_write_text`). Verify they satisfy the required behavior; do not create parallel helpers or repeat security logic in callers:

    def atomic_write_text(path: Path, content: str, *, mode: int | None = None) -> None:

Required behavior:
- validate path
- create temp sibling
- write
- flush
- fsync where appropriate
- replace atomically
- preserve intended permissions

If an existing helper fails any required behavior, fix the helper centrally and update callers. Do not fork it.

## Step 6 — Coverage tests

First inventory the existing `tests/security/` coverage from Session 8 (path safety, symlink escape, atomic-write preservation, partial-failure rollback). Add new test files only where gaps exist; extend existing files where they don't. Do not duplicate or weaken Session 8's tests. Follow existing tests/ naming conventions.

Candidate new files where gaps exist:
- tests/security/test_write_path_coverage.py
- tests/security/test_symlink_escape.py
- tests/security/test_atomic_write.py

Tests must assert traversal attempts fail. Do not use vague `pytest.raises(Exception)` when a precise project exception exists (for example `PathPolicyError`).

## Step 7 — Static heuristic

Create: scripts/audit_write_paths.py

It may use Python AST to list candidate direct writes. The script is reviewer assistance only; do not claim AST detection proves security. Exclude the audit script itself from its own scan. Example shape:

    WRITE_ATTRS = {"write_text", "write_bytes"}
    OPEN_MODES = {"w", "wb", "a", "ab"}
    # Walk AST and print candidate writes for manual review.

## Step 8 — Run

    python scripts/audit_write_paths.py
    pytest -q
    python -m compileall core adapters hooks scripts
    git diff --check

## Exit condition

All external writes are either:
- centrally guarded;
- inside controlled staging/temp directories; or
- explicitly documented as a native system operation that has its own safety/ownership contract.

## STOP / BLOCKED

Report BLOCKED and do not guess if:
- A write site cannot be centrally guarded without redesigning unrelated code.
- Guarding a site would require changing public behavior from an earlier session.
- Session 8's validator or exception type does not exist where expected and cannot be located.
- The control plane and the code conflict and no higher-authority rule resolves it.

Do not invent a workaround silently.

## Completion

On PASS:
1. Update `raw/00_PROJECT_MANIFEST.json`: set `current_baseline` to "Session 12 completed", update `status`, remove `12` from `next_sessions`.
2. Update the README control-plane baseline line to Session 12.
3. Commit per AGENTS.md, then `git pull --rebase origin main`, then push.

## Commit

    git add core tests scripts docs raw/00_PROJECT_MANIFEST.json README.md
    git commit -m "test: enforce path and symlink safety across all write paths"
