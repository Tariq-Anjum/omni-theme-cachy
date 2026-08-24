"""Minimal CLI for omni-theme-cachy.

Wired in pyproject.toml as the ``omni-theme`` console script. Session 02
exposes only theme validation; activation subcommands arrive with later
sessions.

Usage::

    omni-theme theme validate default
    omni-theme theme validate ~/themes/mine --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from core.errors import ThemeError
from core.theme_loader import find_theme
from core.validation import validate_theme_dir

DEFAULT_THEMES_ROOT = Path("themes")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="omni-theme",
        description="Universal theming engine for CachyOS + KDE Plasma 6.",
    )
    sub = parser.add_subparsers(dest="group", required=True)

    theme = sub.add_parser("theme", help="theme inspection and validation")
    theme_sub = theme.add_subparsers(dest="command", required=True)

    validate = theme_sub.add_parser(
        "validate", help="validate a theme directory (metadata, colors, wallpaper)"
    )
    validate.add_argument("reference", help="theme id, name or path")
    validate.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_THEMES_ROOT,
        help="directory to search for themes (default: %(default)s)",
    )
    validate.add_argument("--json", action="store_true", help="emit JSON report")
    validate.add_argument(
        "--strict",
        action="store_true",
        help="also fail on warnings (errors always fail)",
    )
    return parser


def _cmd_theme_validate(args: argparse.Namespace) -> int:
    try:
        theme_dir = find_theme(args.root, args.reference)
    except ThemeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    issues = validate_theme_dir(theme_dir)
    if args.json:
        payload = {
            "theme": str(theme_dir),
            "ok": not any(i.is_error for i in issues),
            "issues": [
                {"severity": i.severity, "code": i.code, "message": i.message}
                for i in issues
            ],
        }
        print(json.dumps(payload, indent=2))
    else:
        print(f"validating {theme_dir}")
        if not issues:
            print("OK: no issues found")
        for issue in issues:
            print(f"  {issue}")

    has_errors = any(i.is_error for i in issues)
    has_warnings = any(not i.is_error for i in issues)
    if has_errors:
        return 1
    return 1 if has_warnings and args.strict else 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.group == "theme" and args.command == "validate":
            return _cmd_theme_validate(args)
        parser.error(f"unhandled command: {args.group} {getattr(args, 'command', '')}")
    except ThemeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
