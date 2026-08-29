# Session 10 — Reconcile the Implementation with Real Omarchy Quattro Architecture

> Read `raw/00_AGENT_EXECUTION_CONTRACT.md` and `raw/00_PROJECT_MANIFEST.json` first — each exactly once. If output appears truncated, do NOT re-read; proceed with what you have or report BLOCKED naming the exact problem.

## Objective

Perform a factual reconciliation pass against current Omarchy Quattro. This session is a correction gate. Do not assume the earlier interpretation of Omarchy is correct. Where prior sessions (including Session 9) labeled Omarchy claims "inspiration, not verified," this session resolves those labels into verified facts.

## OpenCode tools

Use: read, glob, grep, bash, edit, write, websearch, webfetch.
Use free/open-source tools: rg, fd, python, git, pytest, jq.

## Step 1 — Read the actual Omni model

Read in full:
- core/theme_model.py
- core/theme_loader.py
- core/renderer.py
- core/staging.py
- core/targets.py
- docs/research/OMARCHY_ARCHITECTURE.md
- docs/research/OMARCHY_THEMING.md

## Step 2 — Verify against real Omarchy Quattro

Use websearch/webfetch against:
- https://github.com/basecamp/omarchy/tree/quattro
- https://github.com/basecamp/omarchy/blob/quattro/docs/theming.md
- https://github.com/basecamp/omarchy/blob/quattro/shell/README.md

Do not rely on copied claims from previous sessions. Document exact facts.

Fallback: if websearch/webfetch is unavailable or fails, use `docs/research/*` as the latest snapshot and label any claim you could not re-verify against live sources as "per research snapshot, unverified." Do not report BLOCKED solely because of network failure.

The canonical Omarchy Quattro theming documentation currently describes:
- first-party themes under `themes/<name>/`
- optional user themes under `~/.config/omarchy/themes/<name>/`
- staging under `~/.local/state/omarchy/current/next-theme`
- user templates under `~/.config/omarchy/themed/`
- built-in templates
- semantic `colors.toml`
- `shell.toml` surface/style roles
- theme files taking precedence over generated template output

At the same time, the Omarchy shell itself is a Quickshell/QML system and must not be imported into the KDE engine.

## Step 3 — Keep surfaces.toml

Do not remove `surfaces.toml` merely because current Omarchy has a shell configuration model. Instead document:
- Omni surfaces.toml = adapter-neutral semantic surface model
- Omarchy shell.toml = Omarchy Quickshell shell-specific surface/style model
- Omarchy shell.json = shell configuration/layout/plugin state
- KDE Plasma = native panel/widget/window configuration

These are not one-to-one equivalents.

## Step 4 — Reconcile the divergence doc

Reconcile and rewrite the existing `docs/architecture/DIVERGENCE_FROM_OMARCHY.md` (created in Session 9, where Omarchy claims were labeled "inspiration, not verified"). Upgrade those labels to verified facts using Step 2. Do not delete Session 9's content wholesale; preserve what is still accurate and correct what is not.

Required sections:
- Why Omni uses Omarchy as research
- What Omni borrowed
- What Omni intentionally changed
- Why KDE needs adapters
- Why shell.json is not reproduced
- Why surfaces.toml remains
- What is explicitly out of scope

## Step 5 — Create the divergence audit

Create: scripts/audit_omarchy_divergence.py

```python
from pathlib import Path
import re
import sys

FORBIDDEN = re.compile(r"quickshell|hyprland|\.qml\b", re.I)
ROOTS = ("core", "adapters", "hooks", "scripts", "templates")
SELF_NAME = "audit_omarchy_divergence.py"

def main() -> int:
    hits = []
    for root in ROOTS:
        path = Path(root)
        if not path.exists():
            continue
        for item in path.rglob("*"):
            if not item.is_file():
                continue
            if item.name == SELF_NAME:
                continue  # this audit's own regex contains the forbidden literals
            if item.suffix not in {".py", ".toml", ".json", ".md", ".tpl"}:
                continue
            text = item.read_text(encoding="utf-8", errors="ignore")
            if FORBIDDEN.search(text):
                hits.append(str(item))
    if hits:
        print("Unexpected Hyprland/Quickshell references:")
        for item in hits:
            print(f"  {item}")
        return 1
    print("Clean: no unintended Hyprland/Quickshell leakage.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

Important: a research document describing Omarchy may legitimately contain these terms. The audit targets production code and generated templates, not the research corpus. It also excludes itself, because its own regex contains the forbidden literals.

## Step 6 — Tests

```bash
python scripts/audit_omarchy_divergence.py
pytest -q
```

## Exit condition

The codebase clearly communicates: Omni Theme Engine is KDE Plasma-native and uses portable ideas from Omarchy; it is not an Omarchy port.

## STOP / BLOCKED

Report BLOCKED and do not guess if:
- `docs/research/OMARCHY_ARCHITECTURE.md` or `docs/research/OMARCHY_THEMING.md` is missing and live web verification is also unavailable.
- The audit finds real Quickshell/Hyprland/QML leakage in production code that cannot be cleanly resolved without a redesign.
- The control plane and the code conflict and no higher-authority rule resolves it.

Do not invent a workaround silently.

## Completion

On PASS:
1. Update `raw/00_PROJECT_MANIFEST.json`: set `current_baseline` to "Session 10 completed", update `status`, remove `10` from `next_sessions`.
2. Update the README control-plane baseline line to Session 10.
3. Commit per AGENTS.md, then `git pull --rebase origin main`, then push.

## Commit

```bash
git add docs/architecture/DIVERGENCE_FROM_OMARCHY.md scripts/audit_omarchy_divergence.py raw/00_PROJECT_MANIFEST.json README.md
git commit -m "docs: reconcile Omni architecture with real Omarchy Quattro"
```
