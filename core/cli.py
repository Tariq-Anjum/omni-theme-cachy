"""CLI for omni-theme-cachy.

Wired in pyproject.toml as the ``omni`` / ``omni-theme`` console scripts.

Usage::

    omni doctor                      # diagnose environment
    omni version                     # print version
    omni status --json                # show runtime state
    omni theme list                   # list available themes
    omni theme current                # print active theme
    omni theme validate default       # validate theme
    omni theme preview default --json # plan without touching
    omni theme apply default --yes     # full activation
    omni theme rollback --yes          # revert to previous
    omni wallpaper list | current | set <path>

Exit codes (also exported as ``ExitCode``)::

    0   SUCCESS
    2   USAGE                  bad arguments / cancelled confirmation
    10  VALIDATION_ERROR       a theme failed validation
    11  CONFLICT               runtime state is inconsistent
    12  UNSUPPORTED            requested capability unavailable
    13  ACTIVATION_FAILURE     apply/preview could not complete
    14  ROLLBACK_FAILURE       rollback could not complete
    20  INTERNAL_ERROR         unexpected engine failure

Machine-readable mode: every structured command accepts ``--json`` and
then writes a single JSON document to stdout — no progress text, no
warnings in stdout. Human diagnostics go to stderr. ``--yes`` is
required (or a TTY confirmation) for every mutating command.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from enum import IntEnum

from adapters import build_default_registry
from core.color import classify_surface_value
from core.engine import ThemeEngine
from core.errors import ThemeError
from core.theme_loader import find_theme, load_theme_with_overlay
from core.validation import validate_theme, validate_theme_dir

DEFAULT_THEMES_ROOT = Path("themes")


class ExitCode(IntEnum):
    SUCCESS = 0
    USAGE = 2
    VALIDATION_ERROR = 10
    CONFLICT = 11
    UNSUPPORTED = 12
    ACTIVATION_FAILURE = 13
    ROLLBACK_FAILURE = 14
    INTERNAL_ERROR = 20


# ---------------------------------------------------------------------------
# Construction helpers
# ---------------------------------------------------------------------------


def _build_engine(args: argparse.Namespace) -> ThemeEngine:
    kwargs = {
        "themes_root": args.root,
        "adapters": build_default_registry(),
    }
    state_root = getattr(args, "state_root", None)
    if state_root is not None:
        kwargs["state_root"] = state_root
    return ThemeEngine(**kwargs)


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
        payload = {
            "schema_version": 1,
            "command": "theme.preview" if outcome.dry_run else "theme.apply",
            "ok": outcome.ok,
            "status": outcome.status,
            "phase": outcome.phase,
            "theme": {
                "id": outcome.theme_id,
                "name": outcome.theme_name,
                "source": str(outcome.theme_source) if outcome.theme_source else None,
            },
            "generation": outcome.generation,
            "previous_generation": outcome.previous_generation,
            "core_changed": outcome.core_changed,
            "dry_run": outcome.dry_run,
            "rollback_performed": outcome.rollback_performed,
            "adapters": [r.to_dict() for r in outcome.adapter_results],
            "targets": list(outcome.planned_targets),
            "conflicts": [
                {
                    "target": str(c.target),
                    "managed_hash": c.managed_hash,
                    "actual_hash": c.actual_hash,
                }
                for c in outcome.conflicts
            ],
            "capabilities": [
                {
                    "id": c.id,
                    "supported": c.supported,
                    "reason": c.reason,
                    "version": c.version,
                }
                for c in outcome.capabilities
            ],
            "warnings": list(outcome.warnings),
            "errors": list(outcome.errors),
        }
        print(json.dumps(payload, indent=2))
        return ExitCode.SUCCESS if outcome.ok else ExitCode.ACTIVATION_FAILURE
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
    return ExitCode.SUCCESS if outcome.ok else ExitCode.ACTIVATION_FAILURE


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
    parser.add_argument(
        "--state-root", type=Path, help="override state root for testing"
    )
    parser.add_argument("--json", action="store_true", help="emit JSON report")


def _cmd_theme_validate(args: argparse.Namespace) -> int:
    command = "theme.validate"
    try:
        theme_dir = find_theme(args.root, args.reference)
    except ThemeError as exc:
        if args.json:
            print(
                json.dumps(
                    {
                        "schema_version": 1,
                        "command": command,
                        "theme": args.reference,
                        "ok": False,
                        "issues": [
                            {"severity": "error", "code": "THEME_NOT_FOUND",
                             "message": str(exc)}
                        ],
                    },
                    indent=2,
                )
            )
        else:
            print(f"error: {exc}", file=sys.stderr)
        return ExitCode.INTERNAL_ERROR

    issues = validate_theme_dir(theme_dir)
    has_errors = any(i.is_error for i in issues)
    if args.json:
        payload = {
            "schema_version": 1,
            "command": command,
            "theme": str(theme_dir),
            "ok": not has_errors and not (issues and args.strict),
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

    if has_errors:
        return ExitCode.VALIDATION_ERROR
    if any(not i.is_error for i in issues) and args.strict:
        return ExitCode.VALIDATION_ERROR
    return ExitCode.SUCCESS


def _preview_payload(args: argparse.Namespace) -> tuple[dict | None, int]:
    """Read-only theme plan; returns ``(payload, exit_code)``.

    ``payload`` is ``None`` when the theme could not be resolved or
    loaded (a human message is already printed to stderr in that case;
    in ``--json`` mode a JSON failure document is returned instead).
    """
    command = "theme.preview"
    engine = _build_engine(args)
    try:
        theme_dir = find_theme(args.root, args.reference)
    except ThemeError as exc:
        if args.json:
            return ({"schema_version": 1, "command": command, "ok": False,
                     "errors": [str(exc)], "warnings": []}, ExitCode.INTERNAL_ERROR)
        print(f"error: {exc}", file=sys.stderr)
        return (None, ExitCode.INTERNAL_ERROR)

    try:
        theme, _overlay = load_theme_with_overlay(theme_dir, engine._overlay_for(theme_dir))
    except ThemeError as exc:
        if args.json:
            return ({"schema_version": 1, "command": command, "ok": False,
                     "errors": [f"cannot load theme: {exc}"], "warnings": []},
                    ExitCode.INTERNAL_ERROR)
        print(f"error: cannot load theme: {exc}", file=sys.stderr)
        return (None, ExitCode.INTERNAL_ERROR)

    issues = validate_theme(theme)
    validation = [
        {"severity": i.severity, "code": i.code, "message": i.message} for i in issues
    ]

    outcome = engine.apply(args.reference, dry_run=True)

    palette = dict(theme.palette.items())
    surfaces = theme.surfaces.groups
    gradients: list[dict] = []
    for group, entries in surfaces.items():
        for key, value in entries.items():
            try:
                kind = classify_surface_value(key, value)
            except Exception:  # noqa: BLE001 — malformed values surface via validation
                continue
            if kind == "gradient":
                gradients.append({"group": group, "key": key, "value": value})

    resolved_wallpaper = theme.resolve_wallpaper() if theme.path else None
    wallpaper = str(resolved_wallpaper) if resolved_wallpaper else None

    payload = {
        "schema_version": 1,
        "command": command,
        "ok": outcome.ok and not any(i["severity"] == "error" for i in validation),
        "status": outcome.status,
        "theme": {
            "id": theme.meta.id,
            "name": theme.meta.name,
            "version": theme.meta.version,
            "mode": theme.mode,
            "source": str(theme.path or theme_dir),
        },
        "palette": palette,
        "surfaces": surfaces,
        "gradients": gradients,
        "wallpaper": wallpaper,
        "validation": validation,
        "adapters": [
            {
                "id": c.id,
                "supported": c.supported,
                "reason": c.reason,
                "version": c.version,
            }
            for c in outcome.capabilities
        ],
        "targets": list(outcome.planned_targets),
        "conflicts": [
            {
                "target": str(c.target),
                "managed_hash": c.managed_hash,
                "actual_hash": c.actual_hash,
            }
            for c in outcome.conflicts
        ],
        "warnings": list(outcome.warnings) + [i["message"] for i in validation
                                              if i["severity"] != "error"],
        "errors": list(outcome.errors),
    }
    return payload, ExitCode.SUCCESS if payload["ok"] else ExitCode.ACTIVATION_FAILURE


def _cmd_theme_preview(args: argparse.Namespace) -> int:
    payload, code = _preview_payload(args)
    if payload is None:
        return code
    if args.json:
        print(json.dumps(payload, indent=2))
        return code

    print(f"theme:     {payload['theme']['name']} ({payload['theme']['id']})")
    print(f"mode:      {payload['theme']['mode']}")
    print(f"wallpaper: {payload['wallpaper'] or '<none>'}")
    print(f"palette:   {len(payload['palette'])} colors")
    print(f"surfaces:  {len(payload['surfaces'])} groups, {len(payload['gradients'])} gradients")
    print(f"targets:   {len(payload['targets'])} files planned")
    for target in payload["targets"]:
        print(f"  -> {target['target']}" + (f"  ({target['adapter']})" if target["adapter"] else ""))
    for capability in payload["adapters"]:
        state = "supported" if capability["supported"] else "unsupported"
        print(f"adapter {capability['id']}: {state}"
              + (f" ({capability['reason']})" if capability["reason"] else ""))
    if payload["conflicts"]:
        print("conflicts:")
        for conflict in payload["conflicts"]:
            print(f"  {conflict['target']} diverged from engine-managed content")
    for warning in payload["warnings"]:
        print(f"warning: {warning}")
    for error in payload["errors"]:
        print(f"error: {error}", file=sys.stderr)
    return code


def _cmd_theme_apply(args: argparse.Namespace) -> int:
    if not args.dry_run and not _confirm(args, f"apply theme {args.reference!r}?"):
        return ExitCode.USAGE
    engine = _build_engine(args)
    try:
        outcome = engine.apply(
            args.reference,
            force=args.force,
            dry_run=args.dry_run,
        )
    except ThemeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return ExitCode.INTERNAL_ERROR
    return _print_outcome(outcome, args.json)


def _cmd_theme_current(args: argparse.Namespace) -> int:
    engine = _build_engine(args)
    current = engine.current_theme()
    if args.json:
        print(json.dumps({"current_theme": current}, indent=2))
    else:
        print(current or "<no theme active>")
    return ExitCode.SUCCESS if current else ExitCode.ACTIVATION_FAILURE


def _cmd_theme_rollback(args: argparse.Namespace) -> int:
    if not _confirm(args, "roll back to the previous generation?"):
        return ExitCode.USAGE
    engine = _build_engine(args)
    try:
        outcome = engine.rollback()
    except ThemeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return ExitCode.ROLLBACK_FAILURE
    return _print_outcome(outcome, args.json)


def _cmd_doctor(args: argparse.Namespace) -> int:
    """Comprehensive read-only diagnostic for the omni-theme-cachy CLI.

    Probes the OS, Plasma session, XDG directories, runtime state and
    every adapter's environment. Never writes, never changes anything.
    """
    import os
    import platform

    from adapters.gtk.detection import detect_gtk
    from adapters.kde.detection import (
        TOOL_KREADCONFIG6,
        TOOL_PLASMA_APPLY_COLORSCHEME,
        TOOL_PLASMA_APPLY_WALLPAPERIMAGE,
        TOOL_QDBUS6,
        detect_plasma,
    )
    from adapters.konsole.detection import detect_konsole
    from adapters.vscode.adapter import discover_settings_file
    from core import filesystem
    from core.state import CURRENT_LINK, PREVIOUS_LINK, generation_dir, link_target

    plasma = detect_plasma()
    gtk = detect_gtk()
    konsole = detect_konsole()

    engine = _build_engine(args)
    status = engine.status()
    state_root = engine.state_root

    binaries = {
        TOOL_PLASMA_APPLY_COLORSCHEME: plasma.tool_path(TOOL_PLASMA_APPLY_COLORSCHEME),
        TOOL_PLASMA_APPLY_WALLPAPERIMAGE: plasma.tool_path(TOOL_PLASMA_APPLY_WALLPAPERIMAGE),
        TOOL_KREADCONFIG6: plasma.tool_path(TOOL_KREADCONFIG6),
        TOOL_QDBUS6: plasma.tool_path(TOOL_QDBUS6),
        "kcmshell6": gtk.tools.get("kcmshell6"),
        "konsole": konsole.binary,
    }
    missing_binaries = [name for name, path in binaries.items() if not path]

    xdg = {
        "config": str(filesystem.xdg_config_home()),
        "data": str(filesystem.xdg_data_home()),
        "state": str(filesystem.xdg_state_home()),
    }
    xdg_directories = list(xdg.values())
    writeable = {
        "state_root": os.access(state_root, os.W_OK) or not state_root.exists(),
        "config_root": os.access(filesystem.xdg_config_home(), os.W_OK),
    }

    symlinks = {
        "current": link_target(state_root, CURRENT_LINK),
        "previous": link_target(state_root, PREVIOUS_LINK),
    }

    def _link_ok(gen_id: str | None) -> bool:
        return gen_id is not None and generation_dir(state_root, gen_id).is_dir()

    symlink_integrity = bool(_link_ok(symlinks["current"])) and bool(
        not symlinks["previous"] or _link_ok(symlinks["previous"])
    )

    managed_target_conflicts: list[dict] = []
    for record in engine.read_state().managed_targets:
        try:
            actual = filesystem.sha256_file(record.target)
        except FileNotFoundError:
            managed_target_conflicts.append({"target": record.target, "problem": "missing"})
            continue
        except OSError:
            managed_target_conflicts.append({"target": record.target, "problem": "unreadable"})
            continue
        if actual != record.hash:
            managed_target_conflicts.append({"target": record.target, "problem": "modified"})

    adapter_capabilities = {
        "kde": {
            "plasma_session": plasma.is_plasma_session,
            "plasma_version": plasma.plasmashell_version,
            "tools": dict(plasma.tools),
        },
        "gtk": {
            "installed": gtk.has_gtk(),
            "kde_gtk_integration": gtk.kde_gtk_integration,
            "config_home": str(gtk.config_home),
        },
        "konsole": {
            "installed": konsole.installed,
            "default_profile": konsole.default_profile,
        },
        "vscode": {"installed": discover_settings_file() is not None},
    }

    report = {
        "schema_version": 1,
        "command": "doctor",
        "os": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "desktop": plasma.desktop or "unknown",
        "plasma_version": plasma.plasmashell_version or "unknown",
        "session_type": plasma.session_type or "unknown",
        "python_version": platform.python_version(),
        "missing_binaries": missing_binaries,
        "binaries": {name: (path or None) for name, path in binaries.items()},
        "xdg_directories": xdg_directories,
        "runtime_directory": str(filesystem.omni_state_dir()),
        "writeable": writeable,
        "theme_roots": {
            "shipped": str(engine.themes_root),
            "templates": str(engine.templates_root),
            "user_overlays": str(filesystem.omni_config_dir() / "themes"),
            "user_templates": str(filesystem.omni_config_dir() / "templates"),
        },
        "current_theme": status.current_theme,
        "previous_theme": status.previous_theme,
        "state_consistent": status.consistent,
        "state_details": list(status.details),
        "symlink_integrity": symlink_integrity,
        "managed_target_conflicts": managed_target_conflicts,
        "adapter_capabilities": adapter_capabilities,
        "kde_color_scheme": "available" if plasma.has(TOOL_PLASMA_APPLY_COLORSCHEME) else "unavailable",
        "wallpaper_capability": "available" if plasma.has(TOOL_PLASMA_APPLY_WALLPAPERIMAGE) else "unavailable",
        "gtk_sync": "available" if gtk.kde_gtk_integration else "unavailable",
    }

    if getattr(args, "json", False):
        print(json.dumps(report, indent=2))
        return ExitCode.SUCCESS

    print(f"OS:            {report['os']['system']} {report['os']['release']}")
    print(f"Desktop:       {report['desktop']}")
    print(f"Session:       {report['session_type']}")
    print(f"Plasma:        {report['plasma_version']}")
    print(f"Python:        {report['python_version']}")
    print(f"Runtime dir:   {report['runtime_directory']}")
    if missing_binaries:
        print(f"Missing bins:  {', '.join(missing_binaries)}")
    if not writeable["state_root"]:
        print("error: state root is not writable", file=sys.stderr)
    if not writeable["config_root"]:
        print("error: config root is not writable", file=sys.stderr)
    print(f"State:         {status.current_theme or '<no theme>'}"
          f"{' (consistent)' if status.consistent else ' (INCONSISTENT)'}")
    if status.details:
        for detail in status.details:
            print(f"  detail: {detail}")
    if symlinks["current"]:
        print(f"current ->     {symlinks['current']}")
    if symlinks["previous"]:
        print(f"previous ->    {symlinks['previous']}")
    if managed_target_conflicts:
        print("managed target conflicts:")
        for conflict in managed_target_conflicts:
            print(f"  {conflict['target']}: {conflict['problem']}")
    for aid, capability in sorted(adapter_capabilities.items()):
        print(f"adapter {aid}: {capability}")
    return ExitCode.SUCCESS


def _cmd_version(args: argparse.Namespace) -> int:
    """Report the package version and state/JSON schema version."""
    from core.state import STATE_VERSION
    from importlib.metadata import version as get_version

    try:
        pkg = get_version("omni-theme-cachy")
    except Exception:
        pkg = "unknown"  # not installed; running from source

    if getattr(args, "json", False):
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "command": "version",
                    "package": pkg,
                    "state_schema": STATE_VERSION,
                },
                indent=2,
            )
        )
    else:
        print(f"omni-theme-cachy {pkg} (state schema v{STATE_VERSION})")
    return ExitCode.SUCCESS


def _cmd_theme_list(args: argparse.Namespace) -> int:
    """List available themes."""
    from core.theme_loader import load_theme

    themes = []
    root = Path(getattr(args, "root", DEFAULT_THEMES_ROOT))
    if root.is_dir():
        for item in sorted(root.iterdir()):
            if item.is_dir() and (item / "theme.toml").exists():
                try:
                    theme = load_theme(item)
                    theme_info = {
                        "name": theme.meta.name,
                        "id": theme.meta.id,
                        "version": theme.meta.version,
                        "mode": theme.meta.mode,
                    }
                    themes.append(theme_info)
                except Exception:
                    themes.append({"name": item.name, "id": item.name})

    if getattr(args, "json", False):
        print(json.dumps(themes, indent=2))
        return ExitCode.SUCCESS

    if not themes:
        print("No themes found in themes directory")
        return ExitCode.USAGE

    print("Available themes:")
    for theme in themes:
        print(f"  - {theme['name']} ({theme['id']})")

    return ExitCode.SUCCESS


def _cmd_status(args: argparse.Namespace) -> int:
    engine = _build_engine(args)
    status = engine.status()
    payload = status.to_dict()
    if args.json:
        json_payload = {
            "schema_version": 1,
            "command": "status",
            **payload,
        }
        print(json.dumps(json_payload, indent=2))
    else:
        if not status.state_exists:
            print("no state: no theme has been activated yet")
            return ExitCode.SUCCESS
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
    return ExitCode.SUCCESS if status.consistent else ExitCode.CONFLICT


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
        return ExitCode.INTERNAL_ERROR
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
    return ExitCode.SUCCESS


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
            return ExitCode.VALIDATION_ERROR
    return ExitCode.SUCCESS


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
        return ExitCode.INTERNAL_ERROR

    if not _confirm(args, f"set wallpaper to {source}?"):
        return ExitCode.USAGE

    backend, env = _wallpaper_backend()
    if not env.has("plasma-apply-wallpaperimage"):
        print(
            "error: plasma-apply-wallpaperimage is required but not installed",
            file=sys.stderr,
        )
        return ExitCode.INTERNAL_ERROR

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
        return ExitCode.INTERNAL_ERROR

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
    return ExitCode.SUCCESS if verified else ExitCode.VALIDATION_ERROR


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

    list_cmd = theme_sub.add_parser("list", help="list available themes")
    list_cmd.add_argument("--root", type=Path, default=DEFAULT_THEMES_ROOT)
    list_cmd.add_argument("--state-root", type=Path, help="override state root for testing")
    list_cmd.add_argument("--json", action="store_true", help="emit JSON report")

    validate = theme_sub.add_parser(
        "validate", help="validate a theme directory (metadata, colors, wallpaper)"
    )
    validate.add_argument("reference", help="theme id, name or path")
    validate.add_argument(
        "--root", type=Path, default=DEFAULT_THEMES_ROOT,
        help="directory to search for themes (default: %(default)s)",
    )
    validate.add_argument("--state-root", type=Path, help="override state root for testing")
    validate.add_argument("--json", action="store_true", help="emit JSON report")
    validate.add_argument(
        "--strict", action="store_true",
        help="also fail on warnings (errors always fail)",
    )

    preview = theme_sub.add_parser(
        "preview",
        help="plan an activation without touching anything (read-only)",
        epilog="example: omni theme preview tokyo --json",
    )
    _add_theme_reference_args(preview)

    apply_cmd = theme_sub.add_parser(
        "apply",
        help="activate a theme atomically (write; requires --yes)",
        epilog="example: omni theme apply tokyo --yes",
    )
    _add_theme_reference_args(apply_cmd)
    apply_cmd.add_argument("--force", action="store_true",
                            help="overwrite user-modified managed targets")
    apply_cmd.add_argument("--dry-run", action="store_true",
                            help="plan only; equivalent to 'theme preview'")
    apply_cmd.add_argument("--yes", action="store_true",
                            help="skip the confirmation prompt")

    current = theme_sub.add_parser("current", help="print the active theme id")
    current.add_argument("--root", type=Path, default=DEFAULT_THEMES_ROOT)
    current.add_argument("--state-root", type=Path, help="override state root for testing")
    current.add_argument("--json", action="store_true")

    rollback = theme_sub.add_parser(
        "rollback",
        help="revert to the previous generation (write; requires --yes)",
        epilog="example: omni theme rollback --yes",
    )
    rollback.add_argument("--root", type=Path, default=DEFAULT_THEMES_ROOT)
    rollback.add_argument("--state-root", type=Path, help="override state root for testing")
    rollback.add_argument("--json", action="store_true")
    rollback.add_argument("--yes", action="store_true",
                           help="skip the confirmation prompt")

    status = sub.add_parser("status", help="runtime state overview")
    status.add_argument("--root", type=Path, default=DEFAULT_THEMES_ROOT)
    status.add_argument("--state-root", type=Path, help="override state root for testing")
    status.add_argument("--json", action="store_true")

    wall = sub.add_parser("wallpaper", help="wallpaper inspection and control")
    wall_sub = wall.add_subparsers(dest="command", required=True)

    wlist = wall_sub.add_parser("list", help="list known wallpapers")
    wlist.add_argument("--root", type=Path, default=DEFAULT_THEMES_ROOT)
    wlist.add_argument("--state-root", type=Path, help="override state root for testing")
    wlist.add_argument("--json", action="store_true")

    wcur = wall_sub.add_parser("current", help="show the active wallpaper(s)")
    wcur.add_argument("--state-root", type=Path, help="override state root for testing")
    wcur.add_argument("--json", action="store_true")

    wset = wall_sub.add_parser(
        "set",
        help="apply an image as the wallpaper (write; requires --yes)",
        epilog="example: omni wallpaper set ~/wallpapers/deep.jpg --yes",
    )
    wset.add_argument("path", help="image file to apply")
    wset.add_argument("--root", type=Path, default=DEFAULT_THEMES_ROOT)
    wset.add_argument("--state-root", type=Path, help="override state root for testing")
    wset.add_argument("--json", action="store_true")
    wset.add_argument("--yes", action="store_true", help="skip confirmation prompt")

    doctor = sub.add_parser(
        "doctor",
        help="diagnose the environment (read-only)",
        epilog="example: omni doctor --json  # machine-readable diagnostic",
    )
    doctor.add_argument(
        "--root", type=Path, default=DEFAULT_THEMES_ROOT,
        help="directory to search for themes (default: %(default)s)",
    )
    doctor.add_argument(
        "--state-root", type=Path, help="override state root for testing"
    )
    doctor.add_argument("--json", action="store_true", help="emit JSON report")

    version = sub.add_parser(
        "version",
        help="print version information",
        epilog="example: omni version --json",
    )
    version.add_argument("--json", action="store_true", help="emit JSON report")

    parser.epilog = (
        "Safety: theme apply, theme rollback and wallpaper set are "
        "write commands and require --yes in non-interactive use; "
        "validate/preview/status/doctor/list/current/version are "
        "read-only. Every structured command accepts --json."
    )
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
            ("theme", "list"): _cmd_theme_list,
            ("status", None): _cmd_status,
            ("wallpaper", "list"): _cmd_wallpaper_list,
            ("wallpaper", "current"): _cmd_wallpaper_current,
            ("wallpaper", "set"): _cmd_wallpaper_set,
            ("doctor", None): _cmd_doctor,
            ("version", None): _cmd_version,
        }[(args.group, getattr(args, "command", None))]
        return handler(args)
    except ThemeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return ExitCode.INTERNAL_ERROR
    except KeyError:
        parser.error(
            f"unhandled command: {args.group} {getattr(args, 'command', '')}"
        )
    return ExitCode.INTERNAL_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
