"""Wallpaper → palette extraction for omni-theme-cachy.

Derives a complete omni palette (the same role vocabulary as
``themes/default/colors.toml``) from an image, with **no third-party
dependencies required**: images are decoded by Pillow when it is
installed (fast path, all formats) and otherwise by a built-in pure
stdlib PNG decoder (zlib + struct), which covers every shipped theme
wallpaper and the common desktop-wallpaper case.

K-means clustering runs in pure Python with a fixed seed, so the same
image always produces the same palette — daemon re-runs are stable and
testable. Clusters are merged, ranked and mapped to semantic roles:

* the darkest large cluster becomes the background family;
* the lightest becomes the foreground family;
* the most *saturated* mid-luminance cluster becomes the accent, with
  hue-rotated status/terminal hues derived from it;
* the ANSI ramp (``color0``–``color15``) is generated from the terminal
  hue set plus surface ramps so terminals stay readable.

Everything raises :class:`WallpaperExtractionError` (a
:class:`core.errors.ThemeError`) on unreadable, unsupported or
degenerate input — callers can catch the one engine base class.
"""

from __future__ import annotations

import colorsys
import math
import random
import struct
import zlib
from pathlib import Path

from core.color import contrast_ratio, strip_hex
from core.errors import ThemeError

__all__ = [
    "WallpaperColorExtractor",
    "WallpaperExtractionError",
    "PALETTE_ROLES",
]

#: Every role a generated palette provides (order = generated file order).
PALETTE_ROLES: tuple[str, ...] = (
    # Surfaces
    "background", "darker_background", "dark_background", "lighter_background",
    # Text
    "foreground", "bright_foreground", "light_foreground", "dark_foreground",
    "muted",
    # Interaction
    "accent", "accent_secondary", "selection",
    # Status
    "success", "warning", "error", "info",
    # Terminal base hues
    "red", "green", "yellow", "blue", "magenta", "cyan",
    # Terminal bright hues
    "bright_red", "bright_green", "bright_yellow", "bright_blue",
    "bright_magenta", "bright_cyan",
    # ANSI ramp
    *(f"color{i}" for i in range(16)),
)


class WallpaperExtractionError(ThemeError):
    """An image could not be decoded or yielded no usable palette."""


# ---------------------------------------------------------------------------
# Image decoding
# ---------------------------------------------------------------------------

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
#: Above this many pixels the pure-Python PNG path declines (decoding is
#: O(pixels) unfiltering); Pillow handles arbitrarily large images fast.
_PNG_MAX_PIXELS = 2_500_000


def _decode_image(path: Path, sample: int) -> list[tuple[int, int, int]]:
    """Return an RGB pixel sample list for *path* (at most ~sample² pixels)."""
    data = path.read_bytes()
    pixels: list[tuple[int, int, int]] | None = None
    if data.startswith(_PNG_SIGNATURE):
        pixels = _decode_png(data)
    if pixels is None:
        pixels = _decode_via_pillow(path)
    if pixels is None:
        raise WallpaperExtractionError(
            f"cannot decode image {path}: not a PNG (install Pillow for "
            "JPEG/WebP/HEIF support)"
        )
    return _subsample(pixels, sample)


def _decode_via_pillow(path: Path) -> list[tuple[int, int, int]] | None:
    """Pillow fast path; None when Pillow is unavailable."""
    try:
        from PIL import Image  # noqa: PLC0415 — optional dependency
    except ImportError:
        return None
    try:
        with Image.open(path) as img:
            rgba = img.convert("RGB")
            return list(rgba.getdata())
    except Exception as exc:  # noqa: BLE001 — any decode failure is caller-reported
        raise WallpaperExtractionError(f"cannot decode image {path}: {exc}") from exc


def _decode_png(data: bytes) -> list[tuple[int, int, int]] | None:
    """Minimal PNG decoder (stdlib only).

    Supports bit depth 8 (16-bit is accepted and reduced to its high
    byte), color types 0/2/3/4/6, non-interlaced. Returns None when the
    stream is valid PNG but outside those constraints — Pillow may still
    handle it. Malformed streams raise WallpaperExtractionError.
    """
    offset = 8
    width = height = bit_depth = color_type = interlace = None
    palette: list[tuple[int, int, int]] = []
    idat: list[bytes] = []
    while offset + 8 <= len(data):
        (length,), raw_type = struct.unpack_from(">I", data, offset), data[offset + 4:offset + 8]
        body = data[offset + 8:offset + 8 + length]
        offset += 12 + length  # body + type + CRC
        if raw_type == b"IHDR":
            width, height, bit_depth, color_type, _comp, _filt, interlace = struct.unpack(
                ">IIBBBBB", body
            )
        elif raw_type == b"PLTE":
            palette = [tuple(body[i:i + 3]) for i in range(0, len(body) - 2, 3)]
        elif raw_type == b"IDAT":
            idat.append(body)
        elif raw_type == b"IEND":
            break
    if width is None:
        raise WallpaperExtractionError("PNG stream has no IHDR chunk")
    if width <= 0 or height <= 0:
        raise WallpaperExtractionError(f"PNG has degenerate dimensions {width}x{height}")
    if interlace != 0:
        return None  # Adam7: leave it to Pillow
    if bit_depth == 16:
        reduce_16 = True
    elif bit_depth == 8:
        reduce_16 = False
    else:
        return None  # 1/2/4-bit depths: leave it to Pillow

    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type)
    if channels is None:
        return None
    if color_type == 3 and not palette:
        raise WallpaperExtractionError("palette PNG without a PLTE chunk")

    try:
        raw = zlib.decompress(b"".join(idat))
    except zlib.error as exc:
        raise WallpaperExtractionError(f"corrupt PNG (zlib): {exc}") from exc

    stride = width * channels
    bpp = channels  # bytes per pixel for the filter step (8-bit channels)
    out: list[tuple[int, int, int]] = []
    prev = bytearray(stride)
    pos = 0
    if len(raw) < (stride + 1) * height:
        raise WallpaperExtractionError("truncated PNG pixel data")
    for _row in range(height):
        filter_kind = raw[pos]
        pos += 1
        line = bytearray(raw[pos:pos + stride])
        pos += stride
        if filter_kind == 1:  # Sub
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif filter_kind == 2:  # Up
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif filter_kind == 3:  # Average
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif filter_kind == 4:  # Paeth
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pred) & 0xFF
        elif filter_kind != 0:
            raise WallpaperExtractionError(f"unknown PNG filter {filter_kind}")

        if color_type == 2:      # RGB
            out.extend((line[i], line[i + 1], line[i + 2]) for i in range(0, stride, 3))
        elif color_type == 6:    # RGBA — drop alpha
            out.extend((line[i], line[i + 1], line[i + 2]) for i in range(0, stride, 4))
        elif color_type == 0:    # Grayscale
            out.extend(((line[i],) * 3 for i in range(stride)))
        elif color_type == 4:    # Gray + alpha
            out.extend(((line[i],) * 3 for i in range(0, stride, 2)))
        elif color_type == 3:    # Indexed
            out.extend(palette[line[i]] for i in range(stride))

        if reduce_16:
            prev = bytearray(line[0::2])
        else:
            prev = line
    return out


def _subsample(
    pixels: list[tuple[int, int, int]], sample: int
) -> list[tuple[int, int, int]]:
    """Cap the pixel list near ``sample * sample`` with a stride pattern."""
    total = len(pixels)
    if not total:
        raise WallpaperExtractionError("image contains no pixels")
    budget = sample * sample
    if total <= budget:
        return pixels
    stride = math.ceil(math.sqrt(total / budget))
    return pixels[::stride]


# ---------------------------------------------------------------------------
# Color math (all on "#rrggbb" strings)
# ---------------------------------------------------------------------------


def _clamp(v: int) -> int:
    return 0 if v < 0 else (255 if v > 255 else v)


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    """``#rrggbb`` (or ``#rgb``) → ``(r, g, b)``; raises on malformed input."""
    try:
        stripped = strip_hex(value)
    except ThemeError as exc:
        raise WallpaperExtractionError(str(exc)) from exc
    if len(stripped) == 3:
        stripped = "".join(ch * 2 for ch in stripped)
    if len(stripped) != 6:
        raise WallpaperExtractionError(f"not a #rrggbb color: {value!r}")
    return int(stripped[0:2], 16), int(stripped[2:4], 16), int(stripped[4:6], 16)


def rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{_clamp(r):02x}{_clamp(g):02x}{_clamp(b):02x}"


def _mix(c1: str, c2: str, t: float) -> str:
    r1, g1, b1 = hex_to_rgb(c1)
    r2, g2, b2 = hex_to_rgb(c2)
    return rgb_to_hex(
        round(r1 + (r2 - r1) * t), round(g1 + (g2 - g1) * t), round(b1 + (b2 - b1) * t)
    )


def _scale(c: str, factor: float) -> str:
    r, g, b = hex_to_rgb(c)
    return rgb_to_hex(round(r * factor), round(g * factor), round(b * factor))


def _luminance(c: str) -> float:
    r, g, b = hex_to_rgb(c)
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0


def _saturation(c: str) -> float:
    r, g, b = (v / 255.0 for v in hex_to_rgb(c))
    mx, mn = max(r, g, b), min(r, g, b)
    return 0.0 if mx == 0 else (mx - mn) / mx


def _shift_hue(c: str, degrees: float, *, sat_boost: float = 1.0, min_sat: float = 0.0) -> str:
    r, g, b = (v / 255.0 for v in hex_to_rgb(c))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    h = (h + degrees / 360.0) % 1.0
    s = min(1.0, max(min_sat, s * sat_boost))
    r2, g2, b2 = colorsys.hls_to_rgb(h, l, s)
    return rgb_to_hex(round(r2 * 255), round(g2 * 255), round(b2 * 255))


def _with_lightness(c: str, target: float, *, raise_lum: bool) -> str:
    """Move *c*'s HLS lightness to *target* (only in the given direction),
    keeping hue and saturation — legibility without desaturating."""
    r, g, b = (v / 255.0 for v in hex_to_rgb(c))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    new_l = max(l, target) if raise_lum else min(l, target)
    if l == 0.0 and s == 0.0:  # pure black/white anchors gain a little chroma
        s = 0.35
    r2, g2, b2 = colorsys.hls_to_rgb(h, new_l, s)
    return rgb_to_hex(round(r2 * 255), round(g2 * 255), round(b2 * 255))


# ---------------------------------------------------------------------------
# K-means (pure Python, deterministic)
# ---------------------------------------------------------------------------


def _dist2(a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


def _kmeans(
    pixels: list[tuple[int, int, int]], k: int, max_iter: int = 16, seed: int = 0x0A7C
) -> list[tuple[int, int, int, int]]:
    """Return up to *k* clusters as ``(r, g, b, weight)`` (weight = pixel count)."""
    rng = random.Random(seed)
    # k-means++ seeding: spread the initial centers across the image.
    centers: list[tuple[int, int, int]] = [pixels[rng.randrange(len(pixels))]]
    while len(centers) < k:
        distances = [min(_dist2(p, c) for c in centers) for p in pixels]
        total = sum(distances)
        if total == 0:
            break
        pick, acc = rng.random() * total, 0.0
        for pixel, d in zip(pixels, distances):
            acc += d
            if acc >= pick:
                centers.append(pixel)
                break
        else:
            centers.append(pixels[-1])

    assignments: list[int] = [0] * len(pixels)
    for _ in range(max_iter):
        changed = False
        for index, pixel in enumerate(pixels):
            best, best_d = assignments[index], _dist2(pixel, centers[assignments[index]])
            for ci in range(len(centers)):
                d = _dist2(pixel, centers[ci])
                if d < best_d:
                    best, best_d = ci, d
            if best != assignments[index]:
                assignments[index] = best
                changed = True
        # Recompute centers.
        sums = [[0, 0, 0, 0] for _ in centers]
        for pixel, ci in zip(pixels, assignments):
            bucket = sums[ci]
            bucket[0] += pixel[0]
            bucket[1] += pixel[1]
            bucket[2] += pixel[2]
            bucket[3] += 1
        for ci, bucket in enumerate(sums):
            if bucket[3]:
                centers[ci] = (
                    bucket[0] // bucket[3], bucket[1] // bucket[3], bucket[2] // bucket[3]
                )
        if not changed:
            break

    counts = [0] * len(centers)
    for ci in assignments:
        counts[ci] += 1
    clusters = [
        (c[0], c[1], c[2], n) for c, n in zip(centers, counts) if n > 0
    ]
    # Merge clusters that are visually the same color (ΔE-ish, squared).
    merged: list[tuple[int, int, int, int]] = []
    for cluster in sorted(clusters, key=lambda c: -c[3]):
        for index, kept in enumerate(merged):
            if _dist2(cluster[:3], kept[:3]) < 1200:
                weight = kept[3] + cluster[3]
                r = (kept[0] * kept[3] + cluster[0] * cluster[3]) // weight
                g = (kept[1] * kept[3] + cluster[1] * cluster[3]) // weight
                b = (kept[2] * kept[3] + cluster[2] * cluster[3]) // weight
                merged[index] = (r, g, b, weight)
                break
        else:
            merged.append(cluster)
    return merged


# ---------------------------------------------------------------------------
# The extractor
# ---------------------------------------------------------------------------


class WallpaperColorExtractor:
    """Extract an omni role palette from a wallpaper image."""

    def __init__(
        self,
        *,
        n_colors: int = 8,
        sample_size: int = 200,
        max_iter: int = 16,
        seed: int = 0x0A7C,
    ) -> None:
        if not 2 <= n_colors <= 16:
            raise ValueError("n_colors must be between 2 and 16")
        self.n_colors = n_colors
        self.sample_size = sample_size
        self.max_iter = max_iter
        self.seed = seed

    def extract(self, image_path: str | Path) -> dict[str, str]:
        """Semantic role → ``#rrggbb`` for the image at *image_path*."""
        path = Path(image_path)
        if not path.is_file():
            raise WallpaperExtractionError(f"wallpaper image not found: {path}")
        try:
            pixels = _decode_image(path, self.sample_size)
        except WallpaperExtractionError:
            raise
        except OSError as exc:
            raise WallpaperExtractionError(f"cannot read {path}: {exc}") from exc

        clusters = _kmeans(pixels, self.n_colors, self.max_iter, self.seed)
        if not clusters:
            raise WallpaperExtractionError(f"no usable colors in {path}")

        # Background: the best "surface" color — heavy pixels, low saturation,
        # with a bias toward the calm dark surfaces desktop themes expect
        # (a light theme emerges naturally from bright minimal wallpapers).
        # Background: the best "surface" color — heavy pixels, low saturation,
        # with a bias toward the calm dark surfaces desktop themes expect
        # (a light theme emerges naturally from bright minimal wallpapers).
        def _surface_score(c: tuple[int, int, int, int]) -> float:
            hx = rgb_to_hex(*c[:3])
            score = c[3] * (1.0 - 0.85 * _saturation(hx)) ** 2
            if _luminance(hx) < 0.45:
                score *= 2.0
            return score

        bg_cluster = max(clusters, key=_surface_score)
        background = rgb_to_hex(*bg_cluster[:3])
        dark = _luminance(background) < 0.5

        # Foreground: the most luminance-extreme cluster on the *other* side,
        # preferring calm (usable-as-text) candidates.
        others = [c for c in clusters if c is not bg_cluster]
        if others:
            others.sort(key=lambda c: _luminance(rgb_to_hex(*c[:3])), reverse=dark)
            fg_cluster = next(
                (c for c in others if _saturation(rgb_to_hex(*c[:3])) < 0.6),
                others[0],
            )
            foreground = rgb_to_hex(*fg_cluster[:3])
        else:
            foreground = background
        # Near-monochrome images collapse both extremes onto one color; force
        # a readable foreground so the palette never becomes single-valued.
        if _dist2(hex_to_rgb(background), hex_to_rgb(foreground)) < 3000:
            foreground = (
                _mix(background, "#ffffff", 0.82) if dark
                else _mix(background, "#000000", 0.8)
            )
        return self._build_palette(background, foreground, clusters)

    # -- role mapping ---------------------------------------------------------

    def _build_palette(
        self,
        background: str,
        foreground: str,
        ranked: list[tuple[int, int, int, int]],
    ) -> dict[str, str]:
        dark = _luminance(background) < 0.5

        def _contrast_floor(color: str, min_ratio: float) -> str:
            """Step *color*'s lightness away from the background until it
            reaches roughly *min_ratio*:1 WCAG contrast (best effort)."""
            if contrast_ratio(color, background) >= min_ratio:
                return color
            for _ in range(8):
                c = _luminance(color)
                if dark:
                    step_size = max(0.07, (0.97 - c) / 2)
                    color = _with_lightness(
                        color, min(0.97, c + step_size), raise_lum=True
                    )
                else:
                    step_size = max(0.07, c / 2)
                    color = _with_lightness(
                        color, max(0.03, c - step_size), raise_lum=False
                    )
                if contrast_ratio(color, background) >= min_ratio:
                    break
            return color

        foreground = _contrast_floor(foreground, 4.6)

        # Accent: the most saturated cluster in the middle luminance band,
        # falling back to a hue-shifted foreground on near-monochrome images.
        midband = [
            c for c in ranked
            if 0.15 < _luminance(rgb_to_hex(*c[:3])) < 0.85
            and _dist2(c[:3], hex_to_rgb(background)) > 2000
            and _dist2(c[:3], hex_to_rgb(foreground)) > 2000
        ]
        if midband:
            # Prefer saturated clusters, weighted toward readable luminance.
            def _accent_score(c: tuple[int, int, int, int]) -> float:
                hx = rgb_to_hex(*c[:3])
                return _saturation(hx) * (0.35 + _luminance(hx))
            accent = rgb_to_hex(*max(midband, key=_accent_score)[:3])
        else:
            # Monochrome wallpaper: re-voice the background's own hue as a
            # vivid accent instead of washing out the gray foreground.
            source = background if dark else foreground
            accent = _shift_hue(source, 0.0, sat_boost=1.8, min_sat=0.5)
            accent = _with_lightness(
                accent, 0.55 if dark else 0.45, raise_lum=dark
            )

        # Accent legibility: visible on the background, never near-white.
        accent_lum = _luminance(accent)
        if dark and accent_lum < 0.38:
            accent = _with_lightness(accent, 0.45, raise_lum=True)
        elif not dark and accent_lum > 0.55:
            accent = _with_lightness(accent, 0.45, raise_lum=False)
        elif dark and accent_lum > 0.75:
            accent = _with_lightness(accent, 0.7, raise_lum=False)
        accent = _contrast_floor(accent, 3.2)

        accent_secondary = _shift_hue(accent, 40.0, sat_boost=0.9, min_sat=0.25)
        if _dist2(hex_to_rgb(accent), hex_to_rgb(accent_secondary)) < 1500:
            accent_secondary = _shift_hue(accent, 160.0, sat_boost=0.9, min_sat=0.25)
        secondary_lum = _luminance(accent_secondary)
        if dark and secondary_lum < 0.32:
            accent_secondary = _with_lightness(accent_secondary, 0.4, raise_lum=True)
        elif not dark and secondary_lum > 0.6:
            accent_secondary = _with_lightness(accent_secondary, 0.45, raise_lum=False)
        accent_secondary = _contrast_floor(accent_secondary, 2.8)

        muted = _mix(foreground, background, 0.55)
        muted = _contrast_floor(muted, 3.2)

        palette: dict[str, str] = {
            # Surfaces — role names track luminance in both modes.
            "background": background,
            "darker_background": _mix(background, "#000000", 0.25),
            "dark_background": _mix(background, "#000000", 0.12),
            "lighter_background": _mix(background, "#ffffff", 0.05),
            # Text
            "foreground": foreground,
            "bright_foreground": _mix(foreground, "#ffffff" if dark else "#000000", 0.3),
            "light_foreground": _mix(foreground, "#ffffff", 0.35),
            "dark_foreground": _mix(foreground, background, 0.45),
            "muted": muted,
            # Interaction
            "accent": accent,
            "accent_secondary": accent_secondary,
            "selection": _mix(background, accent, 0.30),
        }

        # Status + terminal hues are anchored on the accent hue so the whole
        # theme keeps one color story, but anchored far enough apart to be
        # distinguishable (success green, warning amber, error red, info blue).
        anchor = _shift_hue(accent, 0.0, sat_boost=1.0, min_sat=0.45)
        status = {
            "success": _shift_hue(anchor, 95.0, sat_boost=0.75, min_sat=0.35),
            "warning": _shift_hue(anchor, 180.0, sat_boost=0.85, min_sat=0.45),
            "error": _shift_hue(anchor, 300.0, sat_boost=1.0, min_sat=0.5),
            "info": _shift_hue(anchor, 40.0, sat_boost=0.85, min_sat=0.4),
        }
        if _luminance(background) > 0.5:
            status = {k: _scale(v, 0.75) for k, v in status.items()}
        status = {k: _contrast_floor(v, 3.0) for k, v in status.items()}
        palette.update(status)

        terminal = {
            "red": palette["error"],
            "green": palette["success"],
            "yellow": palette["warning"],
            "blue": palette["info"],
            "magenta": _shift_hue(anchor, 260.0, sat_boost=0.8, min_sat=0.4),
            "cyan": _shift_hue(anchor, 130.0, sat_boost=0.7, min_sat=0.3),
        }
        terminal = {k: _contrast_floor(v, 3.0) for k, v in terminal.items()}
        palette.update(terminal)
        palette.update({
            f"bright_{name}": _contrast_floor(
                _mix(value, "#ffffff" if dark else "#000000", 0.28), 2.5
            )
            for name, value in terminal.items()
        })

        # ANSI ramp: 0/8 are surface steps, 1-7 follow the terminal hues,
        # 9-15 their bright variants, 7/15 readable whites.
        bright_names = {
            9: "red", 10: "green", 11: "yellow",
            12: "blue", 13: "magenta", 14: "cyan",
        }
        for index in range(16):
            if index == 0:
                palette[f"color{index}"] = (
                    _mix(background, "#ffffff", 0.08) if dark
                    else _mix(background, "#000000", 0.55)
                )
            elif index == 7:
                palette[f"color{index}"] = _mix(foreground, background, 0.1)
            elif index == 8:
                palette[f"color{index}"] = (
                    _mix(background, foreground, 0.25) if dark
                    else _mix(background, "#000000", 0.35)
                )
            elif index == 15:
                palette[f"color{index}"] = (
                    _mix(foreground, "#ffffff", 0.5) if dark
                    else _mix(foreground, "#000000", 0.3)
                )
            elif index < 8:
                palette[f"color{index}"] = palette[{
                    1: "red", 2: "green", 3: "yellow",
                    4: "blue", 5: "magenta", 6: "cyan",
                }[index]]
            else:
                palette[f"color{index}"] = palette[f"bright_{bright_names[index]}"]
        return palette
