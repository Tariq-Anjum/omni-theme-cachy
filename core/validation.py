"""Theme validation for omni-theme-cachy.

Two entry points:

* :func:`validate_theme` — rule-check an already-loaded :class:`Theme`
  (pure, no filesystem access beyond nothing).
* :func:`validate_theme_dir` — load a directory and report everything,
  including problems that prevent loading. Never raises for a broken
  theme; problems come back as :class:`Issue` records so the CLI can
  print them all. Pass ``strict=True`` to get exceptions instead.

Thresholds are not invented: text pairs are checked against the WCAG 2.x
AA minimum of **4.5:1**, and accent/status/UI-component pairs against the
WCAG large-text/UI minimum of **3.0:1**. Both produce *warnings* — a low
contrast ratio is a design signal, not a hard failure.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from core.color import classify_surface_value, contrast_ratio, strip_hex
from core.errors import (
    ColorError,
    SurfaceValueError,
    ThemeError,
    ThemeValidationError,
)
from core.theme_loader import _read_toml, load_theme
from core.theme_model import (
    KNOWN_SURFACE_GROUPS,
    REQUIRED_COLORS,
    SURFACES_FILE,
    THEME_FILE,
    Palette,
    Theme,
)

__all__ = ["Severity", "Issue", "validate_theme", "validate_theme_dir"]

Severity = str  # "error" | "warning"

#: WCAG 2.x AA minima, by pair kind.
TEXT_CONTRAST_MIN = 4.5
UI_CONTRAST_MIN = 3.0

_CONTRAST_PAIRS: tuple[tuple[str, str, float], ...] = (
    # (foreground role, background role, minimum ratio)
    ("foreground", "background", TEXT_CONTRAST_MIN),
    ("bright_foreground", "background", TEXT_CONTRAST_MIN),
    ("muted", "background", TEXT_CONTRAST_MIN),
    ("foreground", "selection", TEXT_CONTRAST_MIN),
    ("accent", "background", UI_CONTRAST_MIN),
    ("success", "background", UI_CONTRAST_MIN),
    ("warning", "background", UI_CONTRAST_MIN),
    ("error", "background", UI_CONTRAST_MIN),
    ("info", "background", UI_CONTRAST_MIN),
)


@dataclass(frozen=True)
class Issue:
    """One validation finding."""

    severity: Severity
    code: str
    message: str

    @property
    def is_error(self) -> bool:
        return self.severity == "error"

    def __str__(self) -> str:
        return f"{self.severity}: [{self.code}] {self.message}"


def _check_color_syntax(palette: Palette) -> list[Issue]:
    issues = []
    for role, value in sorted(palette.items()):
        try:
            normalized = f"#{strip_hex(value)}"
        except ColorError:
            issues.append(
                Issue(
                    "error",
                    "BAD_COLOR",
                    f"color {role!r} is malformed: {value!r} "
                    "(expected '#RRGGBB' or '#RGB')",
                )
            )
            continue
        if normalized != value:
            issues.append(
                Issue(
                    "error",
                    "NON_NORMALIZED_COLOR",
                    f"color {role!r} must be stored normalized "
                    f"(got {value!r}, expected {normalized!r})",
                )
            )
    return issues


def _check_required_and_unknown(palette: Palette) -> list[Issue]:
    issues = []
    for role in REQUIRED_COLORS:
        if role not in palette:
            issues.append(Issue("error", "MISSING_COLOR", f"missing required color {role!r}"))
    required = set(REQUIRED_COLORS)
    for role in palette:
        if role not in required:
            issues.append(
                Issue(
                    "warning",
                    "UNKNOWN_COLOR",
                    f"unknown color {role!r} (allowed as extra data; "
                    "rename it or add it to SEMANTIC_ROLES if it is universal)",
                )
            )
    return issues


def _check_wallpaper(theme: Theme) -> list[Issue]:
    default = theme.wallpaper.default
    if not default:
        return [
            Issue(
                "warning",
                "NO_WALLPAPER",
                "theme declares no [wallpaper] default; adapters that need one will skip",
            )
        ]
    issues = []
    resolved = (
        theme.resolve_wallpaper()
        if theme.path is not None
        else None
    )
    if resolved is not None:
        if not resolved.is_file():
            issues.append(
                Issue("error", "WALLPAPER_MISSING", f"wallpaper not found: {resolved}")
            )
        # Normalize away '..' components before comparing: Path.relative_to
        # does not resolve them, so an escaped path could otherwise pass.
        escaped = not Path(os.path.normpath(resolved)).is_relative_to(
            Path(os.path.normpath(theme.path))
        )
        if escaped:
            issues.append(
                Issue(
                    "warning",
                    "WALLPAPER_OUTSIDE_THEME",
                    f"wallpaper {default!r} lives outside the theme directory; "
                    "it will not travel with the theme",
                )
            )
    return issues


def _check_contrast(theme: Theme) -> list[Issue]:
    issues = []
    for fg_role, bg_role, minimum in _CONTRAST_PAIRS:
        if fg_role not in theme.palette or bg_role not in theme.palette:
            continue
        ratio = contrast_ratio(theme.palette.get(fg_role), theme.palette.get(bg_role))
        if ratio < minimum:
            issues.append(
                Issue(
                    "warning",
                    "CONTRAST_LOW",
                    f"{fg_role} vs {bg_role}: contrast {ratio:.2f} < {minimum} "
                    "(WCAG 2.x guidance)",
                )
            )
    return issues


def _check_surfaces(theme: Theme) -> list[Issue]:
    """Surface-role rules.

    Surface *keys* are consumer vocabulary (adapters own them), so only
    groups and value syntax are checked; unknown groups warn, malformed
    values error. A theme without any surfaces is usable (adapters fall
    back to palette roles) but warned about.
    """
    if len(theme.surfaces) == 0:
        return [
            Issue(
                "warning",
                "NO_SURFACES",
                f"theme ships no {SURFACES_FILE!r}; UI adapters will fall back "
                "to palette-derived defaults",
            )
        ]
    issues: list[Issue] = []
    known = set(KNOWN_SURFACE_GROUPS)
    for group, entries in sorted(theme.surfaces.items()):
        if group not in known:
            issues.append(
                Issue(
                    "warning",
                    "UNKNOWN_SURFACE_GROUP",
                    f"unknown surface group [{group}] (allowed; consumers may ignore it)",
                )
            )
        for key, value in sorted(entries.items()):
            try:
                classify_surface_value(key, value)
            except (SurfaceValueError, ColorError) as exc:
                issues.append(
                    Issue("error", "SURFACE_BAD_VALUE", f"[{group}] {exc}")
                )
    return issues


def validate_theme(theme: Theme) -> list[Issue]:
    """Rule-check a loaded theme; returns all findings."""
    issues: list[Issue] = []
    issues += _check_color_syntax(theme.palette)
    issues += _check_required_and_unknown(theme.palette)
    issues += _check_wallpaper(theme)
    issues += _check_contrast(theme)
    issues += _check_surfaces(theme)
    return issues


def validate_theme_dir(path: str | Path, *, strict: bool = False) -> list[Issue]:
    """Load and validate the theme directory at *path*.

    Returns every issue found, including load failures as ``LOAD_FAILED``
    errors. With ``strict=True`` raises :class:`ThemeValidationError` when
    any error-severity issue exists.
    """
    theme_path = Path(path).expanduser()
    issues: list[Issue] = []

    if not theme_path.is_dir():
        issues.append(Issue("error", "THEME_DIR_MISSING", f"no such directory: {theme_path}"))
        return _finalize(issues, strict)

    try:
        data = _read_toml(theme_path / THEME_FILE)
        for table in sorted(data):
            if table not in {"theme", "wallpaper", "colors"}:
                issues.append(
                    Issue(
                        "warning",
                        "UNKNOWN_SECTION",
                        f"{THEME_FILE}: ignoring unknown section [{table}]",
                    )
                )
    except ThemeError:
        pass  # reported below by the real load attempt

    try:
        theme = load_theme(theme_path)
    except ThemeError as exc:
        if isinstance(exc, ColorError):
            severity_code = "BAD_COLOR"
        elif isinstance(exc, SurfaceValueError):
            severity_code = "SURFACE_BAD_VALUE"
        else:
            severity_code = "LOAD_FAILED"
        issues.append(
            Issue(
                "error",
                severity_code,
                f"cannot load theme: {exc}",
            )
        )
        return _finalize(issues, strict)

    issues += validate_theme(theme)
    return _finalize(issues, strict)


def _finalize(issues: list[Issue], strict: bool) -> list[Issue]:
    if strict and any(i.is_error for i in issues):
        raise ThemeValidationError(
            f"validation failed with {sum(i.is_error for i in issues)} error(s); "
            f"{len(issues)} issue(s) total",
            issues,
        )
    return issues
