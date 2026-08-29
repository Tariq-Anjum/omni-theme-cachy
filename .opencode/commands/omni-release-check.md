---
description: Run the complete pre-release acceptance gate
agent: build
---

Run the complete pre-release acceptance gate, in order. Stop on critical
failures. Do not tag or push.

1. `git status --short`
2. `python scripts/audit_omarchy_divergence.py`
3. `python scripts/audit_write_paths.py`
4. `pytest -q`
5. `python -m compileall core adapters hooks scripts`
6. `omni commands --json`
7. `omni doctor --json`
8. `omni theme list`
9. `omni theme validate default`
10. `omni theme preview default --json`
11. `git diff --check`

Omni CLI note: in a development checkout use `.venv/bin/omni` if `omni`
is not on PATH. The Omni CLI is the source of truth — never re-implement
its behaviour.
