# Session 08 — Security Hardening, Path Policy, Ownership, Failure Injection

> Preflight: Read `raw/00_AGENT_EXECUTION_CONTRACT.md` and `raw/00_PROJECT_MANIFEST.json` first.
> Apply the `ownership_policy` and `session_8` facts defined in the manifest. This is a hardening
> session over Sessions 01–07; it does not add features.

## Security invariant
theme data != executable code. Never execute commands derived from theme TOML, templates,
filenames, or overlays. Never auto-run third-party hooks.

## Goal
Centralize path validation and ownership checks so every managed filesystem write passes through
one approved validator, and add deterministic tests for path safety, ownership, partial failure,
and rollback. Reuse existing abstractions. Do not redesign the adapter contract.

## Step 1 — Locate the approved write targets (required discovery, not guessing)
Read each of these once:
- core/filesystem.py — XDG-derived runtime/staging roots and the central path-containment helper.
- core/targets.py, core/staging.py, and adapters/* — where managed write destinations are defined.

Extract the approved write-target set into one named allowlist.
- Do NOT assume a function named safe_under() exists. Use the actual containment helper from
  Sessions 03/04, or add it only if truly absent.
- If no approved write-target set exists in code, or any root is as broad as $HOME or /, STOP and
  report BLOCKED. Do not invent targets.

## Step 2 — Audit every write site
grep -RnE "write_text|write_bytes|open\([^)]*['\"]w|os\.replace|os\.rename|os\.symlink|shutil\.copy|shutil\.copytree|mkdir" core adapters hooks scripts
Classify each hit: internal staging write / managed user target / runtime state / cache / temporary
/ system path / unknown. Every managed-user-target and staging write must go through the central
validator from Step 1. Flag unknown paths for review; do not guess.

## Step 3 — Enforce the central policy
The containment helper must:
- canonicalize the path, then resolve symlinks, before validation;
- reject relative traversal and absolute paths outside the approved targets;
- reject sibling-prefix bypasses (/allowed-evil when /allowed is approved);
- reject symlink escapes out of an approved target;
- handle nonexistent final targets;
- never approve root/../root-evil.
Prefer Path.resolve(strict=False) plus explicit containment checks.

## Step 4 — Apply the ownership policy
Apply ownership_policy from the manifest to every destination and its parent dirs:
- reject files/dirs not owned by the current user (including root-owned);
- reject group-writable, world-writable, and setuid/setgid files;
- reject world-writable parent dirs unless the sticky bit is set;
- check after canonicalization + symlink resolution;
- on violation: controlled deterministic failure, preserve the original, no traceback.
Never chown/chmod to "fix" a violation.

## Step 5 — Never silently overwrite user changes
Use the existing staging manifest record schema in core/staging.py (do not invent a new one).
Before overwrite:
- current hash == recorded hash  -> safe to overwrite;
- current hash != recorded hash  -> conflict, stop and report;
- target missing                 -> recreate only if ownership permits.

## Step 6 — Subprocess / execution audit
grep -RnE "subprocess\.|os\.system|shell=True|Popen\(|\.run\(" core adapters hooks scripts
For each: prefer argument arrays, shell=False, fixed executable names, no TOML-derived command
fragments. Any shell=True must have a documented reason or be removed. Do not implement a hook
system in this session.

## Required tests
Create under tests/ (match existing naming; add a tests/security/ group if none exists):
- Path policy: ../../etc/passwd, absolute unrelated path, symlink escape, sibling-prefix, nested
  legal path, nonexistent legal target.
- Write coverage: assert every managed write site routes through the validator.
- Ownership: reject wrong-owner, group/world-writable, setuid; reject world-writable parent
  without sticky.
- Failure/rollback: missing parent dir; read-only destination (original preserved); adapter-2 fails
  after adapter-1 succeeds (adapter-1 rolled back); rollback failure reported and state marked
  unsafe; malformed config (original not overwritten); interrupted promotion; broken or missing
  current/previous symlinks.
- Idempotency: run the apply path twice against an isolated temp root; assert no duplicated
  content, no growing configs, no stray temp files.
Use temporary directories only. Do not test against the real home directory or real desktop.

## Do not
- Do not weaken existing validation to make a fixture pass.
- Do not add system-wide writes, network-dependent tests, or new dependencies.
- Do not run commands that modify the real user's desktop or protected paths.
- Do not do the dedicated KDE .rc INI audit here — that is Session 13.

## Commands
pytest -q
pytest -q tests -k "path or security or rollback or failure or ownership"
python -m compileall core adapters hooks
git diff --check

## Acceptance checklist
- [ ] Every managed filesystem write passes through the central validator.
- [ ] Symlink-escape, sibling-prefix, and traversal attacks covered by tests.
- [ ] Ownership policy enforced per manifest; no auto-repair.
- [ ] User changes never silently overwritten (hash/conflict check).
- [ ] Partial activation failure triggers rollback; failed writes preserve the previous file.
- [ ] No shell=True without a documented reason; no code execution from theme data.
- [ ] Full pytest -q passes; no unrelated files changed.

## Completion
On PASS, update raw/00_PROJECT_MANIFEST.json (current_baseline, status, next_sessions) and commit
with the session work. Commit only the files this session changed.
