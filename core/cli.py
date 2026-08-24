"""CLI for omni-theme-cachy.

Wired in pyproject.toml as the ``omni`` / ``omni-theme`` console scripts.

Usage::

    omni theme validate default
    omni theme preview default --json          # plan only, touches nothing
    omni theme apply default --yes             # full activation
    omni theme current
    omni theme rollback --yes
    omni status --json
    omni wallpaper list | current | set <path>

Exit codes: ``0`` success (VERIFIED / DRY_RUN / ROLLED_BACK),
``1`` degraded or failed activation, ``2`` usage/environment errors.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from adapters import build_default_registry
from core.engine import ThemeEngine
from core.errors import ThemeError
from core.theme_loader import find_theme
from core.validation import validate_theme_dir

DEFAULT_THEMES_ROOT = Path("themes")

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_ERROR = 2


# ---------------------------------------------------------------------------
# Construction helpers
# ---------------------------------------------------------------------------


def _build_engine(args: argparse.Namespace) -> ThemeEngine:
    return ThemeEngine(
        themes_root=args.root,
        adapters=build_default_registry(),
    )


def _confirm(args: argparse.Namespace, prompt: str) -> bool:
    """Honor ``--yes``; ask only on a TTY; refuse otherwise."""
    if getattr(args, "yes", False):
        return True
    if sys.stdin is not None and sys.stdin.isatty():
        answer = input(f"{prompt} [y/N]: ").strip().lower()
        return answer in ("y", "yes")
    print("error: refusing to proceed without --yes (non-interactive shell)", file=sys.stderr)
    return False


def _print_outcome(outcome, as_json: bool) -> int:
    if as_json:
        print(json.dumps(outcome.to_dict(), indent=2))
    else:
        label = outcome.status
        head = f"{label}"
        if outcome.generation:
            head += f" generation {outcome.generation}"
        if outcome.previous_generation:
            head += f" (previous: {outcome.previous_generation})"
        print(head)
        for warning in outcome.warnings:
            print(f"warning: {warning}")
        for error in outcome.errors:
            print(f"error: {error}", file=sys.stderr)
    if not outcome.ok:
        return EXIT_FAILED
    return EXIT_OK if outcome.status != "DEGRADED" else EXIT_FAILED


# ---------------------------------------------------------------------------
# theme validate / preview / apply / current / rollback
# ---------------------------------------------------------------------------


def _add_theme_reference_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("reference", help="theme id, name or path")
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_THEMES_ROOT,
        help="directory to search for themes (default: %(default)s)",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON report")


def _cmd_theme_validate(args: argparse.Namespace) -> int:
    try:
        theme_dir = find_theme(args.root, args.reference)
    except ThemeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

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
        return EXIT_FAILED
    return EXIT_FAILED if has_warnings and args.strict else EXIT_OK


def _cmd_theme_preview(args: argparse.Namespace) -> int:
    engine = _build_engine(args)
    try:
        outcome = engine.apply(args.reference, dry_run=True)
    except ThemeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    return _print_outcome(outcome, args.json)


def _cmd_theme_apply(args: argparse.Namespace) -> int:
    if not args.dry_run and not _confirm(args, f"apply theme {args.reference!r}?"):
        return EXIT_ERROR
    engine = _build_engine(args)
    try:
        outcome = engine.apply(
            args.reference,
            force=args.force,
            dry_run=args.dry_run,
        )
    except ThemeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    return _print_outcome(outcome, args.json)


def _cmd_theme_current(args: argparse.Namespace) -> int:
    engine = _build_engine(args)
    current = engine.current_theme()
    if args.json:
        print(json.dumps({"current_theme": current}, indent=2))
    else:
        print(current or "<no theme active>")
    return EXIT_OK if current else EXIT_FAILED


def _cmd_theme_rollback(args: argparse.Namespace) -> int:
    if not _confirm(args, "roll back to the previous generation?"):
        return EXIT_ERROR
    engine = _build_engine(args)
    try:
        outcome = engine.rollback()
    except ThemeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    return _print_outcome(outcome, args.json)


def _cmd_status(args: argparse.Namespace) -> int:
    engine = _build_engine(args)
    status = engine.status()
    payload = status.to_dict()
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        if not status.state_exists:
            print("no state: no theme has been activated yet")
            return EXIT_FAILED
        print(f"theme:     {status.current_theme or '<none>'}")
        print(f"previous:  {status.previous_theme or '<none>'}")
        print(f"generation:{status.current_generation or '<none>'}")
        print(f"activated: {status.activated_at or '<none>'}")
        print(f"targets:   {status.managed_targets} managed")
        print(f"state:     {'consistent' if status.consistent else 'INCONSISTENT'}")
        for detail in status.details:
            print(f"detail: {detail}")
        for aid, summary in sorted(status.adapters.items()):
            print(f"adapter {aid}: {summary}")
    return EXIT_OK if status.consistent else EXIT_FAILED


# ---------------------------------------------------------------------------
# wallpaper list / current / set
# ---------------------------------------------------------------------------


def _collect_wallpapers(themes_root: Path) -> list[dict]:
    """Shipped theme wallpapers + Omni-cached copies, as report rows."""
    rows: list[dict] = []
    if themes_root.is_dir():
        for theme_dir in sorted(p for p in themes_root.iterdir() if p.is_dir()):
            wall_dir = theme_dir / "wallpapers"
            if not wall_dir.is_dir():
                continue
            for image in sorted(wall_dir.iterdir()):
                if image.is_file():
                    rows.append(
                        {
                            "path": str(image.resolve()),
                            "origin": "theme",
                            "theme": theme_dir.name,
                        }
                    )
    from adapters.kde.adapter import standalone_wallpaper_cache_dir

    cache = standalone_wallpaper_cache_dir()
    if cache.is_dir():
        for image in sorted(cache.iterdir()):
            if image.is_file():
                rows.append(
                    {
                        "path": str(image.resolve()),
                        "origin": "cache",
                        "theme": None,
                    }
                )
    return rows


def _wallpaper_backend():
    from adapters.kde.adapter import KdeAdapter

    adapter = KdeAdapter()
    env = adapter.environment()
    return adapter._backend(), env  # noqa: SLF001 — CLI composition seam


def _cmd_wallpaper_list(args: argparse.Namespace) -> int:
    backend, _env = _wallpaper_backend()
    try:
        active = backend.current_images()
    except ThemeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    rows = _collect_wallpapers(args.root)

    def _is_active(path_text: str) -> bool:
        from pathlib import Path as _P

        try:
            uri = _P(path_text).resolve().as_uri()
        except ValueError:
            return False
        return uri in active

    for row in rows:
        row["active"] = _is_active(row["path"])
    if args.json:
        print(json.dumps({"active": active, "wallpapers": rows}, indent=2))
    else:
        for url in active:
            print(f"active: {url}")
        for row in rows:
            marker = "*" if row["active"] else " "
            print(f"{marker} [{row['origin']:>5}] {row['path']}"
                  + (f" (theme: {row['theme']})" if row["theme"] else ""))
        if not rows:
            print("(no wallpapers found)")
    return EXIT_OK


def _cmd_wallpaper_current(args: argparse.Namespace) -> int:
    backend, _env = _wallpaper_backend()
    images = backend.current_images()
    if args.json:
        print(json.dumps({"images": images}, indent=2))
    else:
        for url in images:
            print(url)
        if not images:
            print("(could not read any active wallpaper)", file=sys.stderr)
            return EXIT_FAILED
    return EXIT_OK


def _cmd_wallpaper_set(args: argparse.Namespace) -> int:
    from adapters.kde.adapter import standalone_wallpaper_cache_dir
    from adapters.kde.config import journal_path
    from adapters.kde.wallpaper import Journal, cache_wallpaper, sniff_image_format
    from core.filesystem import omni_state_dir

    source = Path(args.path).expanduser()
    try:
        sniff_image_format(source)
    except ThemeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if not _confirm(args, f"set wallpaper to {source}?"):
        return EXIT_ERROR

    backend, env = _wallpaper_backend()
    if not env.has("plasma-apply-wallpaperimage"):
        print(
            "error: plasma-apply-wallpaperimage is required but not installed",
            file=sys.stderr,
        )
        return EXIT_ERROR

    state_root = omni_state_dir()
    try:
        cached = cache_wallpaper(source, standalone_wallpaper_cache_dir())
        journal = Journal.load(journal_path(state_root))
        current = backend.current_images()
        journal.remember_pre_omni(current[0] if current else None)
        _name, message = backend.apply_image(cached)
        journal.remember_apply("__direct__", str(cached))
        journal.save()
    except (ThemeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    applied_uri = cached.resolve().as_uri()
    verified = applied_uri in backend.current_images()
    if args.json:
        print(
            json.dumps(
                {
                    "source": str(source),
                    "cached": str(cached),
                    "applied": True,
                    "verified": verified,
                    "message": message,
                },
                indent=2,
            )
        )
    else:
        print(f"applied: {cached}")
        if message:
            print(message)
        print("verified" if verified else "warning: could not confirm via read-back")
    return EXIT_OK if verified else EXIT_FAILED


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="omni",
        description="Universal theming engine for CachyOS + KDE Plasma 6.",
    )
    sub = parser.add_subparsers(dest="group", required=True)

    theme = sub.add_parser("theme", help="theme inspection and activation")
    theme_sub = theme.add_subparsers(dest="command", required=True)

    validate = theme_sub.add_parser(
        "validate", help="validate a theme directory (metadata, colors, wallpaper)"
    )
    validate.add_argument("reference", help="theme id, name or path")
    validate.add_argument(
        "--root", type=Path, default=DEFAULT_THEMES_ROOT,
        help="directory to search for themes (default: %(default)s)",
    )
    validate.add_argument("--json", action="store_true", help="emit JSON report")
    validate.add_argument(
        "--strict", action="store_true",
        help="also fail on warnings (errors always fail)",
    )

    preview = theme_sub.add_parser(
        "preview", help="plan an activation without touching anything"
    )
    _add_theme_reference_args(preview)

    apply_cmd = theme_sub.add_parser("apply", help="activate a theme atomically")
    _add_theme_reference_args(apply_cmd)
    apply_cmd.add_argument("--force", action="store_true",
                           help="overwrite user-modified managed targets")
    apply_cmd.add_argument("--dry-run", action="store_true",
                           help="plan only; equivalent to 'theme preview'")
    apply_cmd.add_argument("--yes", action="store_true",
                           help="skip the confirmation prompt")

    current = theme_sub.add_parser("current", help="print the active theme id")
    current.add_argument("--root", type=Path, default=DEFAULT_THEMES_ROOT)
    current.add_argument("--json", action="store_true")

    rollback = theme_sub.add_parser(
        "rollback", help="revert to the previous generation"
    )
    rollback.add_argument("--root", type=Path, default=DEFAULT_THEMES_ROOT)
    rollback.add_argument("--json", action="store_true")
    rollback.add_argument("--yes", action="store_true",
                          help="skip the confirmation prompt")

    status = sub.add_parser("status", help="runtime state overview")
    status.add_argument("--root", type=Path, default=DEFAULT_THEMES_ROOT)
    status.add_argument("--json", action="store_true")

    wall = sub.add_parser("wallpaper", help="wallpaper inspection and control")
    wall_sub = wall.add_subparsers(dest="command", required=True)

    wlist = wall_sub.add_parser("list", help="list known wallpapers")
    wlist.add_argument("--root", type=Path, default=DEFAULT_THEMES_ROOT)
    wlist.add_argument("--json", action="store_true")

    wcur = wall_sub.add_parser("current", help="show the active wallpaper(s)")
    wcur.add_argument("--json", action="store_true")

    wset = wall_sub.add_parser("set", help="apply an image as the wallpaper")
    wset.add_argument("path", help="image file to apply")
    wset.add_argument("--root", type=Path, default=DEFAULT_THEMES_ROOT)
    wset.add_argument("--json", action="store_true")
    wset.add_argument("--yes", action="store_true", help="skip confirmation prompt")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        handler = {
            ("theme", "validate"): _cmd_theme_validate,
            ("theme", "preview"): _cmd_theme_preview,
            ("theme", "apply"): _cmd_theme_apply,
            ("theme", "current"): _cmd_theme_current,
            ("theme", "rollback"): _cmd_theme_rollback,
            ("status", None): _cmd_status,
            ("wallpaper", "list"): _cmd_wallpaper_list,
            ("wallpaper", "current"): _cmd_wallpaper_current,
            ("wallpaper", "set"): _cmd_wallpaper_set,
        }[(args.group, getattr(args, "command", None))]
        return handler(args)
    except ThemeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except KeyError:
        parser.error(
            f"unhandled command: {args.group} {getattr(args, 'command', '')}"
        )
    return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
