---
description: Run Omni security and write-path audits
agent: build
---

Run the Omni security and write-path audits. Do not modify code unless
the task requires it. Do not push.

1. `python scripts/audit_omarchy_divergence.py`
2. `python scripts/audit_write_paths.py`
3. `pytest -q tests/security`
4. `rg -n "shell=True|os.system\(|subprocess\.Popen|subprocess\.run" core adapters hooks scripts`

Review every flagged subprocess use: argument arrays only, no
`shell=True`, no package-manager calls, no writes outside the approved
roots enforced by `core/filesystem.py`. The Omni CLI is the source of
truth — never re-implement its behaviour.
