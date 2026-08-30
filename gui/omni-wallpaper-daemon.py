#!/usr/bin/env python3
"""Omni Wallpaper Watcher Daemon.

Watches Plasma's wallpaper config and automatically re-themes the
desktop from the new wallpaper using the omni engine (same pipeline as
``omni theme create`` + ``omni theme apply``).

Runs as a systemd --user service or standalone:
  gui/omni-wallpaper-daemon [--interval 3] [--once] [--no-auto-apply]

Service install:
  cp gui/omni-wallpaper-daemon.service ~/.config/systemd/user/
  systemctl --user daemon-reload
  systemctl --user enable --now omni-wallpaper-daemon.service
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import tomllib
from pathlib import Path
from typing import Optional

SCRIPT_DIR = Path(__file__).resolve().parent
OMNI_ROOT_CANDIDATES = (
    SCRIPT_DIR.parent,
    Path.home() / ".local" / "share" / "omni-theme-cachy",
    Path.cwd(),
)

OMNI_ROOT: Optional[Path] = None
for _candidate in OMNI_ROOT_CANDIDATES:
    if (_candidate / "core" / "engine.py").is_file():
        OMNI_ROOT = _candidate
        break
if OMNI_ROOT is None:
    print("ERROR: omni-theme-cachy engine not found next to the daemon.", file=sys.stderr)
    sys.exit(1)
sys.path.insert(0, str(OMNI_ROOT))

from adapters import build_default_registry  # noqa: E402
from core.engine import ThemeEngine  # noqa: E402
from core.theme_factory import create_theme_dir  # noqa: E402
from core.wallpaper_extractor import WallpaperColorExtractor  # noqa: E402

PLASMA_WALLPAPER_CONFIG = (
    Path.home() / ".config" / "plasma-org.kde.plasma.desktop-appletsrc"
)
DAEMON_STATE_FILE = Path.home() / ".config" / "omni-theme-settings" / "daemon-state.json"

THEMES_ROOT = OMNI_ROOT / "themes"
TEMPLATES_ROOT = OMNI_ROOT / "templates"


def log(message: str) -> None:
    print(f"[omni-daemon] {message}", flush=True)


def get_plasma_wallpaper() -> Optional[str]:
    """Read the active Plasma wallpaper path (file:// URIs included)."""
    if not PLASMA_WALLPAPER_CONFIG.is_file():
        return None
    try:
        candidates: list[str] = []
        for line in PLASMA_WALLPAPER_CONFIG.read_text(
            encoding="utf-8", errors="replace"
        ).splitlines():
            stripped = line.strip()
            if not stripped.startswith("Image="):
                continue
            raw = stripped.split("=", 1)[1].strip()
            path = raw
            if raw.startswith("file://"):
                from urllib.parse import unquote, urlparse

                path = unquote(urlparse(raw).path)
            if path and Path(path).is_file():
                candidates.append(path)
        return candidates[-1] if candidates else None
    except OSError:
        return None


def detect_mode() -> str:
    """Best-effort light/dark from the current global theme."""
    plasmarc = Path.home() / ".config" / "plasmarc"
    try:
        if plasmarc.is_file():
            data = tomllib.loads(plasmarc.read_text(encoding="utf-8", errors="replace"))
            theme = str(data.get("KDE", {}).get("LookAndFeelPackage", "")).lower()
            if "light" in theme:
                return "light"
    except (OSError, tomllib.TOMLDecodeError):
        pass
    return "dark"


def apply_extracted_theme(
    colors: dict[str, str],
    engine: ThemeEngine,
    wallpaper: str,
    theme_name: str,
    mode: str,
    force: bool = True,
) -> dict:
    """Create (idempotently) and apply a wallpaper-derived theme."""
    try:
        theme_dir = create_theme_dir(
            THEMES_ROOT, name=theme_name, colors=colors, mode=mode,
            wallpaper=wallpaper, force=force,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"theme creation failed: {exc}"}
    try:
        outcome = engine.apply(theme_dir.name, force=force)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"apply failed: {exc}", "theme": theme_dir.name}
    result = {
        "ok": bool(outcome.ok),
        "theme": outcome.theme_id or theme_dir.name,
        "status": outcome.status,
        "errors": list(outcome.errors),
    }
    if result["ok"]:
        _reconfigure()
    return result


def _reconfigure() -> None:
    import shutil
    import subprocess

    bus = shutil.which("qdbus6") or shutil.which("qdbus")
    if not bus:
        return
    for service, path, call in (
        ("org.kde.plasmashell", "/PlasmaShell", "org.kde.PlasmaShell.reconfigure"),
        ("org.kde.KWin", "/KWin", "org.kde.KWin.reconfigure"),
    ):
        try:
            subprocess.run([bus, service, path, call], capture_output=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            continue


def notify(title: str, message: str) -> None:
    import subprocess

    try:
        subprocess.run(
            ["notify-send", "-i", "preferences-desktop-theme", title, message],
            capture_output=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Omni Wallpaper Watcher Daemon")
    parser.add_argument("--interval", type=int, default=3,
                        help="polling interval in seconds (default: 3)")
    parser.add_argument("--n-colors", type=int, default=8,
                        help="k-means cluster count, 2-16 (default: 8)")
    parser.add_argument("--auto-apply", dest="auto_apply", action="store_true",
                        default=True, help="apply the extracted theme (default)")
    parser.add_argument("--no-auto-apply", dest="auto_apply", action="store_false",
                        help="extract and log only; do not apply")
    parser.add_argument("--once", action="store_true",
                        help="process the current wallpaper once, then exit")
    args = parser.parse_args()

    log(f"starting | engine: {OMNI_ROOT} | interval: {args.interval}s | "
        f"auto-apply: {args.auto_apply} | colors: {args.n_colors}")

    engine = ThemeEngine(
        themes_root=THEMES_ROOT, templates_root=TEMPLATES_ROOT,
        adapters=build_default_registry(),
    )
    extractor = WallpaperColorExtractor(n_colors=args.n_colors)
    mode = detect_mode()
    last_wallpaper: Optional[str] = None
    cooldown = 0
    processed_once = False

    while True:
        try:
            wallpaper = get_plasma_wallpaper()

            if wallpaper and wallpaper != last_wallpaper:
                if cooldown > 0:
                    cooldown -= 1
                elif Path(wallpaper).is_file():
                    log(f"wallpaper: {wallpaper}")
                    last_wallpaper = wallpaper
                    try:
                        colors = extractor.extract(wallpaper)
                    except Exception as exc:  # noqa: BLE001 — keep the daemon alive
                        log(f"extraction failed: {exc}")
                        colors = None
                    if colors is not None:
                        theme_name = (
                            "Wallpaper " + Path(wallpaper).stem
                            .replace("-", " ").replace("_", " ").title()
                        )
                        if args.auto_apply:
                            result = apply_extracted_theme(
                                colors, engine, wallpaper, theme_name, mode
                            )
                            if result["ok"]:
                                log(f"applied theme: {result['theme']} ({result['status']})")
                                notify(
                                    "Omni Theme",
                                    f"Desktop matched to wallpaper: {Path(wallpaper).name}",
                                )
                            else:
                                log(f"apply failed: {result.get('error') or result.get('errors')}")
                        else:
                            log("preview only (auto-apply disabled)")
                    DAEMON_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
                    DAEMON_STATE_FILE.write_text(json.dumps({
                        "last_wallpaper": wallpaper,
                        "mode": mode,
                        "auto_apply": args.auto_apply,
                        "timestamp": time.time(),
                    }))
                    cooldown = 2  # debounce re-reads while plasmashell settles
                    processed_once = True
            elif wallpaper is None and last_wallpaper is None:
                if args.once and not processed_once:
                    log("no wallpaper found; --once exiting")
                    return 1

            if args.once and processed_once:
                log("--once: done")
                return 0
        except KeyboardInterrupt:
            log("shutting down (SIGINT)")
            return 0
        except Exception as exc:  # noqa: BLE001 — a daemon must not die quietly
            log(f"ERROR: {exc}")
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
