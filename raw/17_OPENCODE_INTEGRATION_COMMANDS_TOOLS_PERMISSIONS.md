# Session 17 — OpenCode Integration: Project Commands, Custom Tools, and Safe Permissions

> Read `raw/00_AGENT_EXECUTION_CONTRACT.md` and `raw/00_PROJECT_MANIFEST.json` first — each exactly once. If output appears truncated, do NOT re-read; proceed with what you have or report BLOCKED naming the exact problem.

## Objective

Integrate Omni with current OpenCode conventions so OpenCode agents can drive the repository through deterministic project commands and, where useful, custom tools. The Omni CLI is the source of truth; OpenCode commands wrap it, they do not re-implement it.

## Resolved facts — read before implementing

The manifest records these decisions for this session:
- `integration.commands_json` = `omni commands --json` (schema_version 1; entries `{name, mutates, supports_yes, supports_json, supports_dry_run}` derived from the live parser in `core/cli.py`; documented in `docs/user/CLI.md`) — resolved in Session 14.
- The confirmed scope for this session: (1) an `opencode.json` config declaring allowed tools, command surface, and permissions; (2) a documented mapping from `omni commands --json` to the OpenCode command surface; (3) a permissions allowlist so read-only omni commands run without prompting.

Do not re-open these decisions.

## OpenCode tools

Use: read, glob, grep, bash, edit, write, websearch, webfetch.
Free/open-source utilities: rg, fd, jq, python, pytest, git.

## Step 1 — Verify the installed OpenCode client

Before writing any files, verify the installed OpenCode version and its actual conventions:

    opencode --version

If `opencode` is not installed, verify file structure only and mark runtime verification as "not verified — opencode not installed." Do not block solely on a missing client.

Current OpenCode conventions (verify against the installed client before relying on them):
- Project Markdown commands live in `.opencode/commands/`.
- Custom tools live in `.opencode/tools/`.
- Tool permissions are declared in `opencode.json`.
- Do NOT use the deprecated `.opencode/command/` path.

If the installed client differs from these conventions, adapt to the client and record the actual conventions used.

## Step 2 — Create or update opencode.json

Create or update `opencode.json` (or the repository's existing OpenCode config) with conservative permissions for theme-related operations. Adapt to the real schema/version used by the installed client.

Example concept:

    {
      "$schema": "https://opencode.ai/config.json",
      "permission": {
        "read": "allow",
        "glob": "allow",
        "grep": "allow",
        "bash": "ask",
        "edit": "ask",
        "webfetch": "allow"
      }
    }

The permission policy:
- read-only discovery → allow
- local test/build → ask or allow according to project policy
- desktop mutation → ask
- git push/tag → ask
- network writes / package installs → deny unless explicitly needed

Read-only omni commands (`omni theme list --json`, `omni status --json`, `omni commands --json`, `omni doctor --json`) must run without prompting.

## Step 3 — Create the project commands

Create `.opencode/commands/` with these five commands. Each wraps the omni CLI; none re-implements it.

`omni-check.md`
- description: Run the complete Omni unit and integration test gate
- agent: build
- Body: inspect git status, AGENTS.md, pyproject.toml; then run (1) `python scripts/audit_omarchy_divergence.py`, (2) `python scripts/audit_write_paths.py`, (3) `pytest -q`, (4) `python -m compileall core adapters hooks scripts`, (5) `git diff --check`. Do not push. Report failures, warnings, changed files, exact file:line locations when applicable.

`omni-preview.md`
- description: Preview an Omni theme without changing desktop state
- agent: build
- Body: run `omni theme preview $ARGUMENTS --json`; parse the JSON and report theme, warnings, conflicts, adapter capabilities, generated targets. Do not apply anything. Do not push.

`omni-apply.md`
- description: Safely apply an Omni theme using dry-run then explicit confirmation
- agent: build
- Body: first run `omni theme apply $ARGUMENTS --dry-run --json`; inspect conflicts and errors; only proceed to `omni theme apply $ARGUMENTS --yes --json` when the dry-run contains no unresolved conflicts or validation errors. Report the final JSON result. Do not push unless explicitly requested.

`omni-security.md`
- description: Run Omni security and write-path audits
- agent: build
- Body: run (1) `python scripts/audit_omarchy_divergence.py`, (2) `python scripts/audit_write_paths.py`, (3) `pytest -q tests/security`, (4) `rg -n "shell=True|os.system\(|subprocess\.Popen|subprocess\.run" core adapters hooks scripts`. Review every flagged subprocess. Do not modify code unless the task requires it. Do not push.

`omni-release-check.md`
- description: Run the complete pre-release acceptance gate
- agent: build
- Body: run in order (1) `git status --short`, (2) `python scripts/audit_omarchy_divergence.py`, (3) `python scripts/audit_write_paths.py`, (4) `pytest -q`, (5) `python -m compileall core adapters hooks scripts`, (6) `omni commands --json`, (7) `omni doctor --json`, (8) `omni theme list`, (9) `omni theme validate default`, (10) `omni theme preview default --json`, (11) `git diff --check`. Stop on critical failures. Do not tag or push.

## Step 4 — Custom tools (only if the CLI is insufficient)

Current OpenCode custom tools are TypeScript/JavaScript definitions that can invoke scripts in any language, living in `.opencode/tools/`. Adapt the tool runtime to the installed OpenCode client (the example below assumes a Bun-style shell; verify before use).

Only create a custom tool if the CLI itself is insufficient. Do not create a custom tool for every CLI command.

Preferred model: OpenCode command → omni CLI. Custom tools are for meaningful agent-facing capabilities that would otherwise require repeated shell orchestration.

Example (adapt to the installed client's tool runtime):

    .opencode/tools/omni-status.ts
    import { tool } from "@opencode-ai/plugin"
    export default tool({
      description: "Return machine-readable Omni theme engine status",
      args: {},
      async execute(_args, context) {
        const result = await Bun.$`omni status --json`
          .cwd(context.worktree)
          .text()
        return result.trim()
      },
    })

## Step 5 — Document the mapping

Document the mapping from `omni commands --json` (Session 14's machine-readable surface) to the OpenCode command surface created in Step 3. Record it in `docs/user/CLI.md` or a new `docs/user/OPENCODE.md`, and reference it from `AGENTS.md`.

## Step 6 — Tests

Create `tests/test_opencode_integration.py`. Validate:
- command files exist;
- frontmatter is parseable;
- command names are unique;
- referenced scripts exist;
- commands do not contain dangerous automatic push/install instructions.

## Step 7 — Verify

    opencode --version
    find .opencode/commands -maxdepth 2 -type f -print
    pytest -q
    git diff --check

Start OpenCode and verify the commands are discoverable using the current `/` command discovery rather than assuming a particular UI label. If `opencode` is not installed, verify file structure only and record runtime verification as "not verified."

## Exit condition

OpenCode can invoke a small set of stable project commands that:
- use the Omni CLI as the source of truth;
- avoid redundant implementation;
- do not silently mutate the desktop;
- do not silently push to GitHub.

## STOP / BLOCKED

Report BLOCKED and do not guess if:
- The installed OpenCode client's command/tool/permission conventions cannot be determined and differ from the documented conventions.
- Creating `opencode.json` would require weakening the permission policy (e.g., allowing silent desktop mutation or silent push).
- A referenced script (`scripts/audit_omarchy_divergence.py`, `scripts/audit_write_paths.py`) does not exist.
- The control plane and the code conflict and no higher-authority rule resolves it.

Do not invent a workaround silently.

## Completion

On PASS:
1. Update `raw/00_PROJECT_MANIFEST.json`:
   - set `integration.opencode_files` to the list of created files (e.g. `opencode.json`, `.opencode/commands/*.md`);
   - set `integration.opencode_schema` to the schema/version used;
   - set `source_evidence.opencode_integration` to `{ "value": "resolved", "source": "Session 17", "status": "RESOLVED" }`;
   - set `current_baseline` to "Session 17 completed", update `status`, remove `17` from `next_sessions`.
2. Update the README control-plane baseline line to Session 17.
3. Commit per AGENTS.md, then `git pull --rebase origin main`, then push.

## Commit

    git add .opencode opencode.json tests docs AGENTS.md raw/00_PROJECT_MANIFEST.json README.md
    git commit -m "feat: integrate Omni with OpenCode project commands and safe tooling"
