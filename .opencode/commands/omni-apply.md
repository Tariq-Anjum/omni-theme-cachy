---
description: Safely apply an Omni theme using dry-run then explicit confirmation
agent: build
---

Safely apply an Omni theme: dry-run first, explicit confirmation second.
Never mutate the desktop silently.

1. Run `omni theme apply $ARGUMENTS --dry-run --json`
   (use `.venv/bin/omni` in a development checkout if `omni` is not on
   PATH).
2. Inspect the JSON: if `conflicts` or `errors` are non-empty, stop and
   report them. Do not proceed to the real apply.
3. Only when the dry-run contains no unresolved conflicts or validation
   errors, run `omni theme apply $ARGUMENTS --yes --json` and report the
   final JSON result (`status`, `targets`, `warnings`).

Do not push unless the user explicitly requests it. The Omni CLI is the
source of truth — never re-implement its behaviour. `--yes` is required
for non-interactive shells; without it a non-TTY apply refuses with exit
code 2.
