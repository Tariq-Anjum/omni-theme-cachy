"""TOML loading of themes for omni-theme-cachy.

Theme layout::

    themes/<theme>/
    ├── theme.toml      # [theme] metadata, [wallpaper]
    ├── colors.toml     # flat table of semantic roles → '#RRGGBB'
    ├── surfaces.toml   # UI surface roles ([popups], [controls], …)
    └── wallpapers/

Colors may alternatively live in a ``[colors]`` table inside
``theme.toml`` (handy for single-file themes); ``colors.toml`` wins when
both exist so user overrides stay predictable. Surfaces follow the same
pattern: ``surfaces.toml`` first, embedded ``[surfaces]`` table second,
and a theme without either loads with an empty surface set (validation
reports that as a warning, since adapters degrade gracefully).

Loading is strict: structural problems raise
:class:`core.errors.ThemeLoadError`, malformed color values raise
:class:`core.errors.ColorError`, and malformed surface values (bad
gradient / border-width / alpha) raise
:class:`core.errors.SurfaceValueError` — all naming the offending key or
role. Tolerant reporting belongs to :mod:`core.validation`.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, replace
from pathlib import Path

from core.color import classify_surface_value
from core.color import strip_hex
from core.errors import ColorError, SurfaceValueError, ThemeLoadError
from core.theme_model import (
    COLORS_FILE,
    REQUIRED_METADATA_FIELDS,
    SURFACES_FILE,
    THEME_FILE,
    VALID_MODES,
    Palette,
    Surfaces,
    Theme,
    ThemeMeta,
    WallpaperConfig,
)

__all__ = [
    "load_theme",
    "load_theme_with_overlay",
    "OverlayReport",
    "discover_themes",
    "find_theme",
]


def _read_toml(path: Path) -> dict:
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    except FileNotFoundError as exc:
        raise ThemeLoadError(f"missing file: {path}") from exc
    except IsADirectoryError as exc:
        raise ThemeLoadError(f"not a file: {path}") from exc
    except OSError as exc:
        raise ThemeLoadError(f"cannot read {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ThemeLoadError(f"invalid TOML in {path}: {exc}") from exc


def _parse_meta(data: dict, source: Path) -> ThemeMeta:
    if not isinstance(data, dict):
        raise ThemeLoadError(f"[theme] table missing or not a table in {source}")
    missing = [k for k in REQUIRED_METADATA_FIELDS if k not in data]
    if missing:
        raise ThemeLoadError(
            f"{source}: [theme] is missing required keys: {', '.join(missing)}"
        )
    name = data["name"]
    theme_id = data["id"]
    version = data["version"]
    mode = data["mode"]

    if not isinstance(name, str) or not name.strip():
        raise ThemeLoadError(f"{source}: theme.name must be a non-empty string")
    if not isinstance(theme_id, str) or not theme_id.strip():
        raise ThemeLoadError(f"{source}: theme.id must be a non-empty string")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ThemeLoadError(f"{source}: theme.version must be a positive integer")
    if mode not in VALID_MODES:
        modes = "/".join(VALID_MODES)
        raise ThemeLoadError(f"{source}: theme.mode must be one of {modes}, got {mode!r}")
    return ThemeMeta(name=name, id=theme_id, version=version, mode=mode)


def _parse_wallpaper(data: dict, source: Path) -> WallpaperConfig:
    if not isinstance(data, dict):
        raise ThemeLoadError(f"{source}: [wallpaper] must be a table")
    default = data.get("default")
    if default is None:
        return WallpaperConfig()
    if not isinstance(default, str) or not default.strip():
        raise ThemeLoadError(f"{source}: wallpaper.default must be a non-empty string path")
    return WallpaperConfig(default=default)


def _parse_colors(raw, source: Path) -> Palette:
    if not isinstance(raw, dict):
        raise ThemeLoadError(f"{source}: colors must be a table of role = \"#RRGGBB\"")
    colors: dict[str, str] = {}
    for role, value in raw.items():
        if not isinstance(value, str):
            raise ColorError(f"{source}: color {role!r} must be a string, got {value!r}")
        try:
            colors[role] = f"#{strip_hex(value)}"
        except ColorError as exc:
            raise ColorError(f"{source}: {exc} (role {role!r})") from None
    return Palette(colors)


def _parse_surfaces(raw, source: Path) -> Surfaces:
    """Validate a ``{group: {key: value}}`` table into :class:`Surfaces`."""
    if not isinstance(raw, dict):
        raise ThemeLoadError(f"{source}: [surfaces] must be a table of tables")
    groups: dict[str, dict[str, object]] = {}
    for group, entries in raw.items():
        if not isinstance(entries, dict):
            raise ThemeLoadError(
                f"{source}: surfaces group [{group}] must be a table of key = value"
            )
        checked: dict[str, object] = {}
        for key, value in entries.items():
            try:
                classify_surface_value(key, value)
            except SurfaceValueError as exc:
                raise SurfaceValueError(f"{source}: {exc}") from None
            except ColorError as exc:
                raise ColorError(f"{source}: {exc}") from None
            checked[key] = value
        groups[group] = checked
    return Surfaces(groups)


def _extract_tables(data: dict) -> tuple[dict | None, dict | None]:
    """Pull embedded ``[colors]``/``[surfaces]`` tables out of theme.toml data."""
    data = dict(data)
    colors = data.pop("colors", None)
    surfaces = data.pop("surfaces", None)
    return colors, surfaces


def load_theme(path: str | Path) -> Theme:
    """Load the theme directory at *path* into a :class:`Theme`.

    *path* must be the theme directory itself (containing ``theme.toml``).
    Raises ThemeLoadError/ColorError with file context on any problem.
    """
    theme_dir = Path(path).expanduser()
    if not theme_dir.is_dir():
        raise ThemeLoadError(f"theme directory not found: {theme_dir}")

    theme_path = theme_dir / THEME_FILE
    data = _read_toml(theme_path)
    if not isinstance(data, dict):
        raise ThemeLoadError(f"{theme_path}: top level must be a TOML table")

    meta_table = data.get("theme")
    if meta_table is None:
        raise ThemeLoadError(f"{theme_path}: missing required [theme] table")
    meta = _parse_meta(meta_table, theme_path)
    wallpaper = (
        _parse_wallpaper(data["wallpaper"], theme_path)
        if "wallpaper" in data
        else WallpaperConfig()
    )

    embedded_colors, embedded_surfaces = _extract_tables(data)

    colors_path = theme_dir / COLORS_FILE
    if colors_path.is_file():
        colors_data = _read_toml(colors_path)
        # Allow either a bare role table or a single [colors]-wrapped table.
        if "colors" in colors_data and isinstance(colors_data["colors"], dict):
            colors_data = colors_data["colors"]
        palette = _parse_colors(colors_data, colors_path)
    elif embedded_colors is not None:
        palette = _parse_colors(embedded_colors, theme_path)
    else:
        raise ThemeLoadError(
            f"{theme_dir}: no colors found "
            f"(expected {COLORS_FILE} or a [colors] table in {THEME_FILE})"
        )

    surfaces_path = theme_dir / SURFACES_FILE
    if surfaces_path.is_file():
        surfaces_data = _read_toml(surfaces_path)
        if "surfaces" in surfaces_data and isinstance(surfaces_data["surfaces"], dict):
            surfaces_data = surfaces_data["surfaces"]
        surfaces = _parse_surfaces(surfaces_data, surfaces_path)
    elif embedded_surfaces is not None:
        surfaces = _parse_surfaces(embedded_surfaces, theme_path)
    else:
        surfaces = Surfaces()

    return Theme(
        meta=meta,
        wallpaper=wallpaper,
        palette=palette,
        surfaces=surfaces,
        path=theme_dir,
    )


def discover_themes(root: str | Path) -> list[Path]:
    """All directories directly under *root* that look like themes."""
    root = Path(root).expanduser()
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir() and (p / THEME_FILE).is_file())


def find_theme(root: str | Path, reference: str | Path) -> Path:
    """Resolve a theme reference (id, name, or explicit path) to its directory.

    Explicit paths win; otherwise *root* is searched for a matching
    directory name or ``theme.id``/``theme.name``. Raises ThemeLoadError
    when nothing matches.
    """
    ref = Path(reference).expanduser()
    if ref.is_absolute() or len(ref.parts) > 1:
        if ref.is_dir() and (ref / THEME_FILE).is_file():
            return ref
        raise ThemeLoadError(f"not a theme directory: {ref}")
    if ref.is_dir() and (ref / THEME_FILE).is_file():
        return ref.resolve()

    root_path = Path(root).expanduser()
    candidate = root_path / str(reference)
    if candidate.is_dir() and (candidate / THEME_FILE).is_file():
        return candidate

    for theme_dir in discover_themes(root_path):
        try:
            data = _read_toml(theme_dir / THEME_FILE)
            meta = data.get("theme") or {}
        except ThemeLoadError:
            continue
        if meta.get("id") == str(reference) or meta.get("name") == str(reference):
            return theme_dir

    raise ThemeLoadError(
        f"no theme matching {str(reference)!r} under {root_path} "
        "(searched by directory name, theme.id and theme.name)"
    )


# ---------------------------------------------------------------------------
# User overlays (Omarchy pattern, session 03)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OverlayReport:
    """Provenance of a user-overlay merge.

    ``colors`` / ``surfaces`` record exactly which keys the overlay set
    (whether it changed the value or restated it), so callers can report
    ownership honestly instead of guessing.
    """

    applied: bool
    colors_path: Path | None = None
    surfaces_path: Path | None = None
    colors: frozenset[str] = frozenset()
    surfaces: frozenset[tuple[str, str]] = frozenset()

    @property
    def ownership(self) -> str:
        """Manifest ownership mode implied by this overlay."""
        return "user-overlay" if self.applied else "base"


def _load_overlay_table(path: Path, wrapper: str) -> dict:
    """Read an overlay TOML file; bare table or single *wrapper*-wrapped."""
    data = _read_toml(path)
    if wrapper in data and isinstance(data[wrapper], dict):
        return data[wrapper]
    return data


def load_theme_with_overlay(
    theme_dir: str | Path,
    overlay_dir: str | Path | None,
) -> tuple[Theme, OverlayReport]:
    """Load *theme_dir* and deep-merge a user overlay on top of it.

    Overlay layout mirrors a theme directory but may contain only the
    files being tweaked::

        ~/.config/omni-theme/themes/<theme>/
        ├── colors.toml     # role = "#RRGGBB" overrides/additions
        └── surfaces.toml   # [group] key = value overrides/additions

    Merging is **key-by-key deep**: overlay color roles replace base
    roles (and may add new ones); surface entries replace at the
    ``(group, key)`` level. Metadata ([theme]) and wallpaper always stay
    with the base theme — a user tweaks values, never identity. A
    missing or empty *overlay_dir* is not an error; the base theme is
    returned untouched with an :class:`OverlayReport` whose
    ``ownership`` is ``"base"``.
    """
    base = load_theme(theme_dir)
    if overlay_dir is None:
        return base, OverlayReport(applied=False)

    overlay_path = Path(overlay_dir).expanduser()
    if not overlay_path.is_dir():
        return base, OverlayReport(applied=False)

    colors_path = overlay_path / COLORS_FILE
    surfaces_path = overlay_path / SURFACES_FILE

    overlay_colors: dict[str, str] = {}
    if colors_path.is_file():
        raw = _load_overlay_table(colors_path, "colors")
        overlay_colors = dict(_parse_colors(raw, colors_path).colors)

    overlay_surfaces: dict[str, dict[str, object]] = {}
    if surfaces_path.is_file():
        raw = _load_overlay_table(surfaces_path, "surfaces")
        parsed = _parse_surfaces(raw, surfaces_path)
        overlay_surfaces = {g: dict(entries) for g, entries in parsed.items()}

    merged_colors = dict(base.palette.colors)
    merged_colors.update(overlay_colors)

    merged_groups: dict[str, dict[str, object]] = {
        group: dict(entries) for group, entries in base.surfaces.groups.items()
    }
    for group, entries in overlay_surfaces.items():
        merged_groups.setdefault(group, {}).update(entries)

    merged = replace(
        base,
        palette=Palette(merged_colors),
        surfaces=Surfaces(merged_groups),
    )
    report = OverlayReport(
        applied=bool(overlay_colors or overlay_surfaces),
        colors_path=colors_path if colors_path.is_file() else None,
        surfaces_path=surfaces_path if surfaces_path.is_file() else None,
        colors=frozenset(overlay_colors),
        surfaces=frozenset(
            (group, key) for group, entries in overlay_surfaces.items() for key in entries
        ),
    )
    return merged, report
