# Session 10 — Reconcile the Implementation with Real Omarchy Quattro Architecture

## Objective

Perform a factual reconciliation pass against current Omarchy Quattro.

This session is a correction gate. Do not assume the earlier interpretation of Omarchy is correct.

The canonical Omarchy Quattro theming documentation currently describes:

- first-party themes under `themes/<name>/`
- optional user themes under `~/.config/omarchy/themes/<name>/`
- staging under `~/.local/state/omarchy/current/next-theme`
- user templates under `~/.config/omarchy/themed/`
- built-in templates
- semantic `colors.toml`
- `shell.toml` surface/style roles
- theme files taking precedence over generated template output. citeturn576446view0

At the same time, the Omarchy shell itself is a Quickshell/QML system and must not be imported into the KDE engine.

## OpenCode tools

Use:

- `read`
- `glob`
- `grep`
- `bash`
- `edit`
- `write`
- `websearch`
- `webfetch`

Use free/open-source tools:

```bash
rg
fd
python
git
pytest
jq
```

## Step 1 — Read actual Omni model

Read:

```text
core/theme_model.py
core/theme_loader.py
core/renderer.py
core/staging.py
core/targets.py
docs/research/OMARCHY_ARCHITECTURE.md
docs/research/OMARCHY_THEMING.md
```

in full.

## Step 2 — Verify Omarchy architecture from source

Use web search/fetch against:

```text
https://github.com/basecamp/omarchy/tree/quattro
https://github.com/basecamp/omarchy/blob/quattro/docs/theming.md
https://github.com/basecamp/omarchy/blob/quattro/shell/README.md
```

Do not rely on copied claims in previous sessions.

Document exact facts.

## Step 3 — Reconcile terminology

Do not remove `surfaces.toml` merely because current Omarchy has a shell configuration model.

Instead document:

```text
Omni surfaces.toml
    = adapter-neutral semantic surface model

Omarchy shell.toml
    = Omarchy Quickshell shell-specific surface/style model

Omarchy shell.json
    = shell configuration/layout/plugin state

KDE Plasma
    = native panel/widget/window configuration
```

These are not one-to-one equivalents.

## Step 4 — Add divergence document

Create:

```text
docs/architecture/DIVERGENCE_FROM_OMARCHY.md
```

Required sections:

```text
Why Omni uses Omarchy as research
What Omni borrowed
What Omni intentionally changed
Why KDE needs adapters
Why shell.json is not reproduced
Why surfaces.toml remains
What is explicitly out of scope
```

## Step 5 — Leakage audit

Create:

```text
scripts/audit_omarchy_divergence.py
```

Use:

```python
from pathlib import Path
import re
import sys

FORBIDDEN = re.compile(r"quickshell|hyprland|\.qml\b", re.I)
ROOTS = ("core", "adapters", "hooks", "scripts", "templates")

def main() -> int:
    hits = []
    for root in ROOTS:
        path = Path(root)
        if not path.exists():
            continue
        for item in path.rglob("*"):
            if not item.is_file():
                continue
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

Important: a research document describing Omarchy may legitimately contain these terms. The audit targets production code and generated templates, not the research corpus.

## Step 6 — Test

```bash
python scripts/audit_omarchy_divergence.py
pytest -q
```

## Exit condition

The codebase clearly communicates:

> Omni Theme Engine is KDE Plasma-native and uses portable ideas from Omarchy; it is not an Omarchy port.

## Commit

```bash
git add docs/architecture/DIVERGENCE_FROM_OMARCHY.md scripts/audit_omarchy_divergence.py
git commit -m "docs: reconcile Omni architecture with real Omarchy Quattro"
```
