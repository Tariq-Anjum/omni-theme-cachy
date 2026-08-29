"""Wallpaper plumbing for the kde adapter (Plasma 6).

Mechanisms — verified live on Plasma 6.7.4 (Wayland), not from memory:

* Apply: ``plasma-apply-wallpaperimage <file>`` (present since Plasma
  5.25; applies the ``org.kde.image`` wallpaper plugin to every screen).
  There is deliberately **no** DBus fallback for applying: qdbus6
  cannot marshal ``setWallpaper``'s ``QVariantMap`` argument reliably,
  and guessing at it would violate the "no guessed legacy commands"
  rule. When the native tool is missing the adapter reports that
  accurately instead.
* Read back: ``qdbus6 org.kde.plasmashell /PlasmaShell evaluateScript``
  walking ``desktops()`` with ``currentConfigGroup =
  ["Wallpaper","org.kde.image","General"]`` and ``readConfig("Image")``
  (verified live). Fallback when qdbus6 is unavailable: scan
  ``~/.config/plasma-org.kde.plasma.desktop-appletsrc`` for
  ``[Containments][n][Wallpaper][org.kde.image][General] Image=…``.

Caching policy: the source image is validated, then copied to an
Omni-owned cache path keyed by content hash. The desktop points at the
*cache*, so a theme never references a file the user later moves or
deletes. Prior user wallpapers are never deleted; the first wallpaper
Omni displaces is journaled so rollback can restore it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from core.errors import AdapterError
from core.filesystem import atomic_copy, atomic_write_text, sha256_file

from adapters.kde.config import run_command
from adapters.kde.detection import TOOL_PLASMA_APPLY_WALLPAPERIMAGE, TOOL_QDBUS6

__all__ = [
    "IMAGE_SIGNATURES",
    "WALLPAPER_PLUGIN",
    "APPLY_BACKEND_NATIVE",
    "Journal",
    "WallpaperBackend",
    "cache_path_for",
    "cache_wallpaper",
    "ensure_cached",
    "sniff_image_format",
]

#: Magic-byte prefixes for image formats plasmashell accepts.
IMAGE_SIGNATURES: tuple[tuple[str, bytes], ...] = (
    ("png", b"\x89PNG\r\n\x1a\n"),
    ("jpeg", b"\xff\xd8\xff"),
    ("gif", b"GIF87a"),
    ("gif", b"GIF89a"),
    ("bmp", b"BM"),
    ("webp", b"RIFF"),  # RIFF container; WEBP verified via offset below
)

#: The only wallpaper plugin we set (Plasma 6 image wallpaper).
WALLPAPER_PLUGIN = "org.kde.image"

APPLY_BACKEND_NATIVE = TOOL_PLASMA_APPLY_WALLPAPERIMAGE

APPLETSRC_FILE = "plasma-org.kde.plasma.desktop-appletsrc"

_SCRIPT_PREFIX = (
    "var out=[]; var ds=desktops(); "
    "for (var i=0;i<ds.length;i++){var d=ds[i]; "
    'd.currentConfigGroup=["Wallpaper",'
)
_SCRIPT_SUFFIX = (
    ',"General"]; '
    'out.push(d.screen+"|"+d.readConfig("Image"));}'
    'print(out.join("\\n"));'
)


def _read_back_script() -> str:
    """JS snippet for evaluateScript (assembled to keep JS braces intact)."""
    return _SCRIPT_PREFIX + json.dumps(WALLPAPER_PLUGIN) + _SCRIPT_SUFFIX


def sniff_image_format(path: str | Path) -> str:
    """Return the image format name for *path* or raise AdapterError."""
    image_path = Path(path)
    if not image_path.is_file():
        raise AdapterError(f"wallpaper image not found: {image_path}")
    try:
        head = image_path.open("rb").read(16)
    except OSError as exc:
        raise AdapterError(f"cannot read wallpaper image {image_path}: {exc}") from exc
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    for name, magic in IMAGE_SIGNATURES:
        if head.startswith(magic):
            return name
    raise AdapterError(
        f"{image_path} is not a recognizable image "
        "(expected png/jpeg/gif/bmp/webp)"
    )


def cache_path_for(
    source: str | Path,
    cache_dir: str | Path,
    *,
    theme_label: str = "omni",
) -> Path:
    """Predicted cache path for *source* **without** copying anything.

    Read-only (hashes the source); lets ``plan()`` stay side-effect-free
    while still naming the exact path :func:`cache_wallpaper` will use.
    """
    source_path = Path(source)
    digest = sha256_file(source_path)
    suffix = source_path.suffix.lower().lstrip(".") or "png"
    return Path(cache_dir) / f"{theme_label}-{digest[:12]}.{suffix}"


def ensure_cached(source: str | Path, target: str | Path) -> Path:
    """Copy *source* onto the exact *target* cache path (idempotent).

    Skips the copy when the cached bytes already match the source;
    repairs a corrupted/drifted cache entry otherwise. The repair goes
    through :func:`core.filesystem.atomic_copy` (write policy + atomic
    replacement), so a rejected or failed copy can never truncate the
    existing cache entry.
    """
    source_path = Path(source)
    target_path = Path(target)
    sniff_image_format(source_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if (
        not target_path.exists()
        or sha256_file(target_path) != sha256_file(source_path)
    ):
        atomic_copy(source_path, target_path)
    return target_path


def cache_wallpaper(
    source: str | Path,
    cache_dir: str | Path,
    *,
    theme_label: str = "omni",
) -> Path:
    """Copy *source* into *cache_dir* under a stable content-keyed name.

    Name format: ``<theme_label>-<sha256[:12]>.<ext>`` — identical input
    always lands on one path, so repeated applies are no-ops at the
    cache layer and distinct content can never collide.
    """
    source_path = Path(source)
    sniff_image_format(source_path)  # validate before anything is copied
    cached = cache_path_for(source_path, cache_dir, theme_label=theme_label)
    return ensure_cached(source_path, cached)


# ---------------------------------------------------------------------------
# Journal: Omni-private record of displaced wallpaper state
# ---------------------------------------------------------------------------


@dataclass
class Journal:
    """Adapter-private record persisted under ``<state>/adapters/kde.json``.

    ``pre_omni_wallpaper`` keeps the *pre-Omni* desktop wallpaper (the
    one Omni displaced first); written once, preserved forever, used as
    the last-resort rollback target. ``history`` maps theme id → the
    cached wallpaper last pushed for it, so rolling back to generation
    of theme T can restore T's own wallpaper rather than something
    stale. Only plain image URLs are recorded; slideshow/directory
    selections cannot be represented and are left untouched.
    """

    #: Maximum remembered theme → wallpaper entries.
    HISTORY_LIMIT = 16

    path: Path
    pre_omni_wallpaper: str | None = None
    #: theme id → cached wallpaper path (insertion-ordered, recent last)
    history: dict[str, str] | None = None

    def __post_init__(self) -> None:
        if self.history is None:
            self.history = {}

    @classmethod
    def load(cls, path: str | Path) -> "Journal":
        journal_path = Path(path)
        try:
            raw = json.loads(journal_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return cls(path=journal_path)
        except (OSError, json.JSONDecodeError):
            # A corrupt record must never brick theming: start fresh but
            # keep the file until the next write replaces it.
            return cls(path=journal_path)
        if not isinstance(raw, dict):
            return cls(path=journal_path)
        pre = raw.get("pre_omni_wallpaper")
        legacy_prev = raw.get("previous_wallpaper")
        history_raw = raw.get("history")
        history: dict[str, str] = {}
        if isinstance(history_raw, dict):
            history = {
                str(k): v
                for k, v in history_raw.items()
                if isinstance(k, str) and isinstance(v, str)
            }
        elif isinstance(raw.get("last_applied_cache"), str):
            # v1 records tracked only "the cache we last pushed"; fold it
            # under an anonymous key so it remains restorable.
            history["<last>"] = raw["last_applied_cache"]
        return cls(
            path=journal_path,
            pre_omni_wallpaper=(
                pre if isinstance(pre, str)
                else legacy_prev if isinstance(legacy_prev, str)
                else None
            ),
            history=history,
        )

    def remember_pre_omni(self, url: str | None) -> bool:
        """Record the pre-Omni wallpaper once; True when newly stored."""
        if self.pre_omni_wallpaper is None and url:
            self.pre_omni_wallpaper = url
            return True
        return False

    def remember_apply(self, theme_label: str, cached: str | Path) -> None:
        assert self.history is not None
        self.history[theme_label] = str(cached)
        while len(self.history) > self.HISTORY_LIMIT:
            self.history.pop(next(iter(self.history)))

    def wallpaper_for(self, theme_label: str | None) -> str | None:
        """Rollback target for the generation being restored.

        Exact theme match wins; an unknown/anonymous context falls back
        to the most recent entry; a *known* theme without an entry gets
        the pre-Omni original (conservative baseline predating every
        Omni change).
        """
        assert self.history is not None
        if theme_label and theme_label in self.history:
            return self.history[theme_label]
        if not theme_label and self.history:
            return self.history[next(reversed(self.history))]
        return self.pre_omni_wallpaper

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {
                "version": 2,
                "pre_omni_wallpaper": self.pre_omni_wallpaper,
                "history": self.history,
            },
            indent=2,
        )
        return atomic_write_text(self.path, payload + "\n")


# ---------------------------------------------------------------------------
# Backend: apply + read back
# ---------------------------------------------------------------------------


class WallpaperBackend:
    """Applies wallpapers through the safest available native mechanism.

    ``runner`` and ``appletsrc_path`` are injectable for hermetic tests.
    """

    def __init__(
        self,
        *,
        tools: Mapping[str, str | None] | None = None,
        runner: Callable[[list[str]], object] = run_command,
        appletsrc_path: str | Path | None = None,
    ) -> None:
        self._tools = dict(tools) if tools else {}
        self._runner = runner
        self._appletsrc = (
            Path(appletsrc_path)
            if appletsrc_path
            else Path.home() / ".config" / APPLETSRC_FILE
        )

    # -- capability -------------------------------------------------------

    def backend_name(self) -> str | None:
        """Preferred apply mechanism on this machine (None: unusable)."""
        if self._tools.get(APPLY_BACKEND_NATIVE):
            return APPLY_BACKEND_NATIVE
        if self._tools.get(TOOL_QDBUS6):
            return APPLY_BACKEND_DBUS
        return None

    def can_read_back(self) -> bool:
        return bool(self._tools.get(TOOL_QDBUS6)) or self._appletsrc.is_file()

    # -- apply -------------------------------------------------------------

    def apply_image(
        self,
        image_path: str | Path,
        *,
        fill_mode: str | None = None,
    ) -> tuple[str, str]:
        """Push *image_path* live; returns ``(backend, tool_message)``.

        Raises AdapterError when the native tool is missing or reports
        failure.
        """
        target = Path(image_path)
        tool = self._tools.get(APPLY_BACKEND_NATIVE)
        if not tool:
            raise AdapterError(
                "wallpaper cannot be applied: plasma-apply-wallpaperimage "
                "is not installed on this system"
            )
        argv = [tool, str(target)]
        if fill_mode:
            argv += ["-f", fill_mode]
        proc = self._runner(argv)  # type: ignore[operator]
        stdout = getattr(proc, "stdout", "") or ""
        stderr = getattr(proc, "stderr", "") or ""
        code = getattr(proc, "returncode", 1)
        if code != 0:
            raise AdapterError(
                f"plasma-apply-wallpaperimage failed (exit {code}): "
                f"{(stderr or stdout).strip()}"
            )
        return APPLY_BACKEND_NATIVE, (stdout or stderr).strip()

    # -- read back -----------------------------------------------------------

    def current_images(self) -> list[str]:
        """Active wallpaper URLs (``file://…``) as reported by Plasma.

        Best-effort: empty list when nothing could be read. The DBus
        scripting route is authoritative; the appletsrc scan is the
        fallback and may briefly lag behind a just-applied change.
        """
        qdbus = self._tools.get(TOOL_QDBUS6)
        if qdbus:
            proc = self._runner([  # type: ignore[operator]
                qdbus,
                "org.kde.plasmashell",
                "/PlasmaShell",
                "org.kde.PlasmaShell.evaluateScript",
                _read_back_script(),
            ])
            if getattr(proc, "returncode", 1) == 0:
                urls = self._parse_script_output(getattr(proc, "stdout", "") or "")
                if urls:
                    return urls
        return self._images_from_appletsrc()

    @staticmethod
    def _parse_script_output(stdout: str) -> list[str]:
        urls: list[str] = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("|", 1)
            url = parts[-1].strip()
            if url and url.lower() != "null":
                urls.append(url)
        return urls

    def _images_from_appletsrc(self) -> list[str]:
        try:
            text = self._appletsrc.read_text(encoding="utf-8")
        except OSError:
            return []
        section_re = re.compile(r"^\[(Containments)\]\[(\d+)\]\[Wallpaper\]"
                                r"\[org\.kde\.image\]\[General\]$")
        images: list[str] = []
        current_section = ""
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                current_section = stripped
                continue
            if current_section and section_re.match(current_section):
                key, sep, value = stripped.partition("=")
                if sep and key.strip() == "Image":
                    value = value.strip()
                    if value and value.lower() != "null":
                        images.append(value)
        return images
