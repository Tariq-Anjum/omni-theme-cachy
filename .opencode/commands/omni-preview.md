---
description: Preview an Omni theme without changing desktop state
agent: build
---

Preview an Omni theme without changing desktop state. Do not apply
anything. Do not push.

1. Run `omni theme preview $ARGUMENTS --json`
   (use `.venv/bin/omni` in a development checkout if `omni` is not on
   PATH).
2. Parse the single JSON document on stdout and report:
   - the theme (id, name, mode) and palette summary;
   - `warnings`, `conflicts`, `errors` (empty means clean);
   - per-adapter capabilities (`adapters[].supported` with `reason`);
   - the generated targets (`targets[]`) and wallpaper.

The Omni CLI is the source of truth — never re-implement its behaviour.
`theme preview` never writes live targets or mutates state.
