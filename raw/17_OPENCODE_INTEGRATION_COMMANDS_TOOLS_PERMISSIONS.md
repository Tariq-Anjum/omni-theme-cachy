# Session 17 — OpenCode Integration, Commands, Tools, and Permissions

> Read `00_AGENT_EXECUTION_CONTRACT.md` and `00_PROJECT_MANIFEST.json` first.

## Agent Objective

Provide a minimal, documented OpenCode integration that exposes safe read and diagnostic operations while protecting state-changing operations with explicit permissions and confirmation.

## Required Deliverables

Inspect the repository's existing OpenCode conventions first. Update only the integration files required for:

- Command definitions.
- Tool definitions.
- Permission declarations.
- Usage documentation.
- Example invocation or fixture tests.

## Permission Model

| Operation | Permission and confirmation |
|---|---|
| Read theme metadata | Read only |
| Preview generated files | Read only |
| Run doctor or status | Read/execute; no write confirmation |
| Apply theme | Write/execute plus explicit confirmation |
| Roll back theme | Write/execute plus explicit confirmation |
| Install integration | Write plus explicit confirmation |

The exact OpenCode schema must match the version and conventions already used in the repository. Do not invent incompatible fields.

## Safety Requirements

- OpenCode commands must invoke the existing CLI or service layer.
- Do not duplicate activation logic in integration glue.
- State-changing operations must retain validation, backup, and rollback behavior.
- The integration must fail clearly when OpenCode is unavailable.
- No secrets may be embedded in command definitions or examples.

## Required Tests

- Command schema validation.
- Read-only operation does not write.
- Apply requires confirmation.
- Rollback requires confirmation.
- Invalid arguments are rejected.
- OpenCode absence produces a controlled diagnostic.

## Do Not Do

- Do not grant unrestricted shell access.
- Do not bypass `--yes` or safety checks.
- Do not make OpenCode a runtime dependency of core activation.
- Do not add unrelated agent tools.

## Commands

```bash
pytest -q
<integration-validator> <integration-files>
<project-cli> doctor
git diff --check
```

Run the actual validator used by the repository, if present, and report when none exists.

## Acceptance Checklist

- [ ] Integration schema matches the project's existing OpenCode convention.
- [ ] Read and write permissions are distinct.
- [ ] State-changing operations require confirmation.
- [ ] Integration delegates to the existing implementation.
- [ ] Tests pass.

## Final Response

Use the format in `00_AGENT_EXECUTION_CONTRACT.md` and stop after Session 17.
