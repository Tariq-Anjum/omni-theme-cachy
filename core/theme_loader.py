"""TOML loading of themes for omni-theme-cachy.

Theme layout::

    themes/<theme>/
    ├── theme.toml      # [theme] metadata, [wallpaper]
    ├── colors.toml     # flat table of semantic roles → '#RRGGBB'
    └── wallpapers/

Colors may alternatively live in a ``[colors]`` table inside
``theme.toml`` (handy for single-file themes); ``colors.toml`` wins when
both exist so user overrides stay predictable.

Loading is strict: structural problems raise :class:`core.errors.ThemeLoadError`
and malformed color values raise :class:`core.errors.ColorError` naming the
offending role. Tolerant reporting belongs to :mod:`core.validation`.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from core.color import strip_hex
from core.errors import ColorError, ThemeLoadError
from core.theme_model import (
    COLORS_FILE,
    REQUIRED_METADATA_FIELDS,
    THEME_FILE,
    VALID_MODES,
    Palette,
    Theme,
    ThemeMeta,
    WallpaperConfig,
)

__all__ = ["load_theme", "discover_themes", "find_theme"]


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


def _extract_colors(theme_data: dict, theme_path: Path) -> tuple[Palette | None, dict]:
    """Return (palette_from_colors_toml_or_None, remaining_theme_tables)."""
    data = dict(theme_data)
    embedded = data.pop("colors", None)
    return (embedded if embedded is not None else None), data


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

    embedded, _remaining = _extract_colors(data, theme_path)

    colors_path = theme_dir / COLORS_FILE
    if colors_path.is_file():
        colors_data = _read_toml(colors_path)
        # Allow either a bare role table or a single [colors]-wrapped table.
        if "colors" in colors_data and isinstance(colors_data["colors"], dict):
            colors_data = colors_data["colors"]
        palette = _parse_colors(colors_data, colors_path)
    elif embedded is not None:
        palette = _parse_colors(embedded, theme_path)
    else:
        raise ThemeLoadError(
            f"{theme_dir}: no colors found "
            f"(expected {COLORS_FILE} or a [colors] table in {THEME_FILE})"
        )

    return Theme(meta=meta, wallpaper=wallpaper, palette=palette, path=theme_dir)


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
