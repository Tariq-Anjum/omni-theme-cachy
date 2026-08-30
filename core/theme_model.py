"""Semantic theme model for omni-theme-cachy.

A theme is *semantic-first*: templates ask for roles (``accent``,
``background``, ``red``…) never for concrete app-specific slots. The
ANSI ramp (``color0``..``color15``) ships alongside the roles as plain
data so terminal/color-scheme adapters can map it per-app.

Everything here is immutable value data (frozen dataclasses); parsing and
I/O live in :mod:`core.theme_loader`, rule-checking in
:mod:`core.validation`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from core.errors import ColorError, ThemeError

__all__ = [
    "THEME_FILE",
    "COLORS_FILE",
    "SURFACES_FILE",
    "WALLPAPER_DIR",
    "REQUIRED_METADATA_FIELDS",
    "VALID_MODES",
    "SEMANTIC_ROLES",
    "ANSI_ROLES",
    "REQUIRED_COLORS",
    "KNOWN_SURFACE_GROUPS",
    "ThemeMeta",
    "WallpaperConfig",
    "Palette",
    "Surfaces",
    "Theme",
]

THEME_FILE = "theme.toml"
COLORS_FILE = "colors.toml"
SURFACES_FILE = "surfaces.toml"
WALLPAPER_DIR = "wallpapers"

#: ``[theme]`` keys every theme must declare.
REQUIRED_METADATA_FIELDS = ("name", "id", "version", "mode")

#: Allowed polarity values mirroring Plasma's scheme polarity.
VALID_MODES = ("dark", "light")

#: Semantic roles a complete theme must define.
SEMANTIC_ROLES: tuple[str, ...] = (
    # brand / interaction
    "accent",
    "accent_secondary",
    "selection",
    "muted",
    # surfaces
    "background",
    "dark_background",
    "darker_background",
    "lighter_background",
    # text
    "foreground",
    "dark_foreground",
    "light_foreground",
    "bright_foreground",
    # status
    "success",
    "warning",
    "error",
    "info",
    # base terminal hues
    "red",
    "green",
    "yellow",
    "blue",
    "magenta",
    "cyan",
    # bright terminal hues
    "bright_red",
    "bright_green",
    "bright_yellow",
    "bright_blue",
    "bright_magenta",
    "bright_cyan",
)

#: The classic 16-color ANSI ramp, required as data (adapters map it).
ANSI_ROLES: tuple[str, ...] = tuple(f"color{i}" for i in range(16))

#: Everything a theme must provide to load cleanly.
REQUIRED_COLORS: tuple[str, ...] = SEMANTIC_ROLES + ANSI_ROLES

#: Surface groups defined by the spec (§4). Other groups are allowed but
#: flagged as warnings so new upstream concepts stay visible.
KNOWN_SURFACE_GROUPS: tuple[str, ...] = (
    "popups", "controls",
    # Shell chrome groups, applied surgically by the plasma-chrome adapter.
    "panel", "kwin", "tooltips",
)


@dataclass(frozen=True)
class ThemeMeta:
    """Contents of the ``[theme]`` metadata table."""

    name: str
    id: str
    version: int
    mode: str

    @property
    def is_dark(self) -> bool:
        return self.mode == "dark"

    @property
    def is_light(self) -> bool:
        return self.mode == "light"


@dataclass(frozen=True)
class WallpaperConfig:
    """Contents of the ``[wallpaper]`` table."""

    #: Path relative to the theme directory (or absolute for user themes);
    #: ``None`` when the theme declares no default wallpaper.
    default: str | None = None

    def resolve(self, theme_dir: Path) -> Path | None:
        """Resolve ``default`` against *theme_dir*; None when unset."""
        if not self.default:
            return None
        path = Path(self.default)
        return path if path.is_absolute() else theme_dir / path


@dataclass(frozen=True)
class Palette:
    """Validated, normalized color assignments (role → ``#rrggbb``)."""

    colors: dict[str, str] = field(default_factory=dict)

    def __contains__(self, role: str) -> bool:
        return role in self.colors

    def __iter__(self):
        return iter(self.colors)

    def __len__(self) -> int:
        return len(self.colors)

    def items(self):
        return self.colors.items()

    def get(self, role: str, default: str | None = None) -> str | None:
        """Color for *role* or *default*; unknown roles are not an error."""
        return self.colors.get(role, default)

    def color(self, role: str) -> str:
        """Color for *role*; raises ColorError when the role is missing."""
        try:
            return self.colors[role]
        except KeyError:
            known = ", ".join(sorted(self.colors)) or "<empty>"
            raise ColorError(
                f"theme has no color {role!r}; defined roles: {known}"
            ) from None

    def require(self, *roles: str) -> dict[str, str]:
        """Colors for all *roles*; raises ColorError listing any missing."""
        missing = [r for r in roles if r not in self.colors]
        if missing:
            raise ColorError(f"theme is missing required colors: {', '.join(missing)}")
        return {r: self.colors[r] for r in roles}


@dataclass(frozen=True)
class Surfaces:
    """UI surface roles from ``surfaces.toml`` (Omarchy ``shell.toml`` analog).

    Values stay **as authored** (strings/ints) for round-trip fidelity —
    the renderer and adapters parse them via
    :mod:`core.color` helpers when they need structure. Syntax is
    enforced at load time; semantics belong to consumers.

    Layout: ``group → key → value``, e.g. ``{"popups": {"border-width": 2}}``.
    """

    groups: dict[str, dict[str, object]] = field(default_factory=dict)

    def group(self, name: str) -> dict[str, object]:
        """Entries of one surface group; empty dict when absent."""
        return self.groups.get(name, {})

    def get(self, group: str, key: str, default=None):
        """Single value; *default* when the group or key is missing."""
        return self.groups.get(group, {}).get(key, default)

    def __contains__(self, group: str) -> bool:
        return group in self.groups

    def __len__(self) -> int:
        return len(self.groups)

    def items(self):
        return self.groups.items()


@dataclass(frozen=True)
class Theme:
    """A fully loaded theme: metadata, wallpaper config, palette, surfaces."""

    meta: ThemeMeta
    wallpaper: WallpaperConfig = field(default_factory=WallpaperConfig)
    palette: Palette = field(default_factory=Palette)
    surfaces: Surfaces = field(default_factory=Surfaces)
    #: Directory the theme was loaded from, when known.
    path: Path | None = None

    def __post_init__(self) -> None:
        if isinstance(self.palette, dict):  # convenience for hand-built themes
            object.__setattr__(self, "palette", Palette(dict(self.palette)))
        if isinstance(self.surfaces, dict):
            object.__setattr__(self, "surfaces", Surfaces(dict(self.surfaces)))

    @property
    def mode(self) -> str:
        return self.meta.mode

    def color(self, role: str) -> str:
        return self.palette.color(role)

    def resolve_wallpaper(self) -> Path | None:
        if self.path is None:
            raise ThemeError("cannot resolve wallpaper: theme has no source path")
        return self.wallpaper.resolve(self.path)
