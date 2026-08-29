---
description: Run the complete Omni unit and integration test gate
agent: build
---

Run the complete Omni test gate. Do not push.

1. Inspect context: `git status --short`, then read `AGENTS.md` and
   `pyproject.toml` for project conventions.
2. Run each gate step in order and stop to report on a critical failure:
   1. `python scripts/audit_omarchy_divergence.py`
   2. `python scripts/audit_write_paths.py`
   3. `pytest -q`
   4. `python -m compileall core adapters hooks scripts`
   5. `git diff --check`

Omni CLI note: in a development checkout the canonical executable may not
be on PATH; use `.venv/bin/omni` (or the installed `omni` shim). The Omni
CLI is the source of truth — never re-implement its behaviour.

Report: failures, warnings, changed files, and exact `file:line` locations
where applicable.
