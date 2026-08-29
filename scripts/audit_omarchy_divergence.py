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
