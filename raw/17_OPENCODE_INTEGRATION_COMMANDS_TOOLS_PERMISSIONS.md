# Session 17 — OpenCode Integration: Project Commands, Custom Tools, and Safe Permissions

## Objective

Integrate Omni with current OpenCode conventions so OpenCode agents can drive the repository through deterministic project commands and, where useful, custom tools.

### Important correction

Current OpenCode documentation uses:

```text
.opencode/commands/
```

for project Markdown commands.

Custom tools belong in:

```text
.opencode/tools/
```

OpenCode also supports tool permissions in `opencode.json`. citeturn950349search1turn950349search0turn950349search7

Do not use the older/inaccurate:

```text
.opencode/command/
```

path.

## OpenCode tools

OpenCode built-ins:

- `read`
- `write`
- `edit`
- `bash`
- `glob`
- `grep`
- `lsp`
- `websearch`
- `webfetch`

Current OpenCode custom integration:

- Markdown commands in `.opencode/commands/`
- TypeScript/JavaScript custom tools in `.opencode/tools/`
- plugins when a reusable event/tool layer is actually warranted

Do not add plugins when simple project commands are sufficient.

## Step 1 — Inspect existing OpenCode files

```bash
find .opencode -maxdepth 3 -type f -print 2>/dev/null || true
test -f AGENTS.md && cat AGENTS.md
```

Do not overwrite an existing `AGENTS.md`.

## Step 2 — OpenCode project commands

Create:

```text
.opencode/commands/
    omni-check.md
    omni-preview.md
    omni-apply.md
    omni-security.md
    omni-release-check.md
```

### `omni-check.md`

```markdown
---
description: Run the complete Omni unit and integration test gate
agent: build
---

Run the repository verification gate for omni-theme-cachy.

Before making changes, inspect:
- git status
- AGENTS.md
- pyproject.toml

Then run:
1. python scripts/audit_omarchy_divergence.py
2. python scripts/audit_write_paths.py
3. pytest -q
4. python -m compileall core adapters hooks scripts
5. git diff --check

Do not push.

Report:
- failures
- warnings
- changed files
- exact file:line locations when applicable
```

### `omni-preview.md`

```markdown
---
description: Preview an Omni theme without changing desktop state
agent: build
---

Run:
omni theme preview $ARGUMENTS --json

Parse the JSON and report:
- theme
- warnings
- conflicts
- adapter capabilities
- generated targets

Do not apply anything.
Do not push.
```

### `omni-apply.md`

```markdown
---
description: Safely apply an Omni theme using dry-run then explicit confirmation
agent: build
---

First run:
omni theme apply $ARGUMENTS --dry-run --json

Inspect conflicts and errors.

Only proceed to:
omni theme apply $ARGUMENTS --yes --json

when the dry-run result contains no unresolved conflicts or validation errors.

Report the final JSON result.
Do not push unless explicitly requested.
```

### `omni-security.md`

```markdown
---
description: Run Omni security and write-path audits
agent: build
---

Run:
1. python scripts/audit_omarchy_divergence.py
2. python scripts/audit_write_paths.py
3. pytest -q tests/security
4. rg -n "shell=True|os.system\\(|subprocess\\.Popen|subprocess\\.run" core adapters hooks scripts

Review every flagged subprocess.

Do not modify code unless the task requires it.
Do not push.
```

### `omni-release-check.md`

```markdown
---
description: Run the complete pre-release acceptance gate
agent: build
---

Run in order:
1. git status --short
2. python scripts/audit_omarchy_divergence.py
3. python scripts/audit_write_paths.py
4. pytest -q
5. python -m compileall core adapters hooks scripts
6. omni commands --json
7. omni doctor --json
8. omni theme list
9. omni theme validate default
10. omni theme preview default --json
11. git diff --check

Stop on critical failures.

Do not tag or push.
```

## Step 3 — Custom tool only when useful

Current OpenCode custom tools are TypeScript/JavaScript definitions that can invoke scripts in any language. They live in `.opencode/tools/`. citeturn950349search0

Only create a custom tool if the CLI itself is insufficient.

Example:

```text
.opencode/tools/omni-status.ts
```

```ts
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
```

Do not create a custom tool for every CLI command.

Preferred model:

```text
OpenCode command
   -> omni CLI
```

Custom tools are for meaningful agent-facing capabilities that would otherwise require repeated shell orchestration.

## Step 4 — Permissions

Create or update:

```text
opencode.json
```

or the repository's existing OpenCode config.

Use conservative permissions for theme-related operations.

Example concept:

```json
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
```

Adapt to the real OpenCode configuration schema/version used by the installed client.

The important policy:

```text
read-only discovery -> allow
local test/build -> ask or allow according to project policy
desktop mutation -> ask
git push/tag -> ask
network writes/package installs -> deny unless explicitly needed
```

## Step 5 — Verify OpenCode integration

Run:

```bash
opencode --version
find .opencode/commands -maxdepth 2 -type f -print
```

Start OpenCode and verify the commands are discoverable.

Use current `/` command discovery rather than assuming a particular UI label.

## Step 6 — Tests

Create:

```text
tests/test_opencode_integration.py
```

Validate:

- command files exist;
- frontmatter is parseable;
- command names are unique;
- referenced scripts exist;
- commands do not contain dangerous automatic push/install instructions.

## Exit condition

OpenCode can invoke a small set of stable project commands that:

- use the Omni CLI as the source of truth;
- avoid redundant implementation;
- do not silently mutate the desktop;
- do not silently push to GitHub.

## Commit

```bash
git add .opencode opencode.json tests AGENTS.md
git commit -m "feat: integrate Omni with OpenCode project commands and safe tooling"
```
