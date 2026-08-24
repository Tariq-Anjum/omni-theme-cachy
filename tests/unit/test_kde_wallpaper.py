"""Unit tests for wallpaper plumbing: sniffing, caching, journal, backend."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.errors import AdapterError  # noqa: E402

from adapters.kde.detection import TOOL_PLASMA_APPLY_WALLPAPERIMAGE, TOOL_QDBUS6  # noqa: E402
from adapters.kde.wallpaper import (  # noqa: E402
    Journal,
    WallpaperBackend,
    cache_wallpaper,
    sniff_image_format,
)

PNG_MAGIC = b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR"


@dataclass
class FakeProc:
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


class FakeRunner:
    def __init__(self, script=None):
        self.calls: list[list[str]] = []
        self.script = script or (lambda argv: FakeProc(0, "ok", ""))

    def __call__(self, argv):
        self.calls.append(list(argv))
        return self.script(argv)


def _tools(**overrides):
    tools = {
        TOOL_PLASMA_APPLY_WALLPAPERIMAGE: "/usr/bin/plasma-apply-wallpaperimage",
        TOOL_QDBUS6: "/usr/bin/qdbus6",
    }
    tools.update(overrides)
    return {k: v for k, v in tools.items() if v is not None}


# --------------------------------------------------------------------------- #
# Image validation


class TestSniffImageFormat:
    def test_png_detected(self, tmp_path):
        image = tmp_path / "w.png"
        image.write_bytes(PNG_MAGIC + b"rest")
        assert sniff_image_format(image) == "png"

    def test_jpeg_detected(self, tmp_path):
        image = tmp_path / "w.jpg"
        image.write_bytes(b"\xff\xd8\xff\xe0" + b"x" * 12)
        assert sniff_image_format(image) == "jpeg"

    def test_webp_detected(self, tmp_path):
        image = tmp_path / "w.webp"
        image.write_bytes(b"RIFF\x24\x00\x00\x00WEBPVP8 ")
        assert sniff_image_format(image) == "webp"

    def test_text_file_rejected(self, tmp_path):
        image = tmp_path / "fake.png"
        image.write_text("definitely not an image")
        with pytest.raises(AdapterError, match="not a recognizable image"):
            sniff_image_format(image)

    def test_missing_file_rejected(self, tmp_path):
        with pytest.raises(AdapterError, match="not found"):
            sniff_image_format(tmp_path / "nope.png")


# --------------------------------------------------------------------------- #
# Caching


class TestCacheWallpaper:
    def test_cache_copy_is_stable_and_content_keyed(self, tmp_path):
        source = tmp_path / "src.png"
        source.write_bytes(PNG_MAGIC)
        cache_root = tmp_path / "cache"

        first = cache_wallpaper(source, cache_root, theme_label="default")
        second = cache_wallpaper(source, cache_root, theme_label="default")
        assert first == second
        assert first.parent == cache_root
        assert first.name.startswith("default-")
        assert first.read_bytes() == PNG_MAGIC

    def test_different_content_different_paths(self, tmp_path):
        a = tmp_path / "a.png"
        b = tmp_path / "b.png"
        a.write_bytes(PNG_MAGIC + b"a")
        b.write_bytes(PNG_MAGIC + b"b")
        ca = cache_wallpaper(a, tmp_path / "cache")
        cb = cache_wallpaper(b, tmp_path / "cache")
        assert ca != cb

    def test_invalid_source_not_cached(self, tmp_path):
        bad = tmp_path / "bad.png"
        bad.write_text("nope")
        with pytest.raises(AdapterError):
            cache_wallpaper(bad, tmp_path / "cache")
        assert not (tmp_path / "cache").exists()

    def test_corrupted_cache_is_repaired(self, tmp_path):
        source = tmp_path / "src.png"
        source.write_bytes(PNG_MAGIC + b"original")
        cache_root = tmp_path / "cache"
        cached = cache_wallpaper(source, cache_root)
        cached.write_bytes(b"tampered")  # simulate corruption
        repaired = cache_wallpaper(source, cache_root)
        assert repaired == cached
        assert repaired.read_bytes() == PNG_MAGIC + b"original"


# --------------------------------------------------------------------------- #
# Journal


class TestJournal:
    def test_missing_journal_starts_empty(self, tmp_path):
        journal = Journal.load(tmp_path / "adapters" / "kde.json")
        assert journal.pre_omni_wallpaper is None
        assert journal.history == {}

    def test_save_load_round_trip(self, tmp_path):
        path = tmp_path / "adapters" / "kde.json"
        journal = Journal.load(path)
        journal.remember_pre_omni("file:///old/wall.png")
        journal.remember_apply("default", "/cache/x.png")
        journal.save()
        raw = json.loads(path.read_text())
        assert raw["pre_omni_wallpaper"] == "file:///old/wall.png"
        assert raw["history"]["default"] == "/cache/x.png"

        reloaded = Journal.load(path)
        assert reloaded.pre_omni_wallpaper == "file:///old/wall.png"
        assert reloaded.history == {"default": "/cache/x.png"}

    def test_corrupt_journal_degrades_to_empty(self, tmp_path):
        path = tmp_path / "adapters" / "kde.json"
        path.parent.mkdir(parents=True)
        path.write_text("{not json")
        journal = Journal.load(path)
        assert journal.pre_omni_wallpaper is None
        # and it can be rewritten
        journal.remember_pre_omni("file:///x")
        journal.save()
        assert Journal.load(path).pre_omni_wallpaper == "file:///x"

    def test_remember_pre_omni_only_once(self, tmp_path):
        journal = Journal.load(tmp_path / "j.json")
        assert journal.remember_pre_omni("file:///first") is True
        assert journal.remember_pre_omni("file:///second") is False
        assert journal.pre_omni_wallpaper == "file:///first"

    def test_legacy_v1_record_migrated(self, tmp_path):
        path = tmp_path / "j.json"
        path.write_text(
            '{"version": 1,'
            ' "previous_wallpaper": "file:///legacy-orig.png",'
            ' "last_applied_cache": "/cache/old.png"}'
        )
        journal = Journal.load(path)
        assert journal.pre_omni_wallpaper == "file:///legacy-orig.png"
        assert journal.wallpaper_for(None) in ("/cache/old.png",
                                               "file:///legacy-orig.png")

    def test_history_limit_enforced(self, tmp_path):
        journal = Journal.load(tmp_path / "j.json")
        for i in range(journal.HISTORY_LIMIT + 4):
            journal.remember_apply(f"theme-{i}", f"/c/{i}.png")
        keys = list(journal.history)
        assert len(keys) == journal.HISTORY_LIMIT
        assert keys[0] == f"theme-{4}"  # oldest evicted

    def test_wallpaper_for_preference_order(self, tmp_path):
        journal = Journal.load(tmp_path / "j.json")
        journal.remember_pre_omni("file:///orig")
        journal.remember_apply("a", "/c/a.png")
        journal.remember_apply("b", "/c/b.png")
        assert journal.wallpaper_for("a") == "/c/a.png"
        # known theme without entry → conservative pre-Omni baseline
        assert journal.wallpaper_for("zzz") == "file:///orig"
        # anonymous context → most recent entry
        assert journal.wallpaper_for(None) == "/c/b.png"
        empty = Journal(path=tmp_path / "e.json", history={})
        assert empty.wallpaper_for("a") is None


# --------------------------------------------------------------------------- #
# Backend


SCRIPT_LINE = "0|file:///wallpapers/one.png"


class TestBackendApply:
    def test_apply_via_native_tool(self, tmp_path):
        runner = FakeRunner()
        backend = WallpaperBackend(tools=_tools(), runner=runner)
        name, message = backend.apply_image(tmp_path / "w.png")
        assert name == "plasma-apply-wallpaperimage"
        assert len(runner.calls) == 1
        assert runner.calls[0][0] == "/usr/bin/plasma-apply-wallpaperimage"
        assert runner.calls[0][1].endswith("w.png")

    def test_apply_failure_raises(self, tmp_path):
        runner = FakeRunner(
            lambda argv: FakeProc(1, "", "cannot open file")
        )
        backend = WallpaperBackend(tools=_tools(), runner=runner)
        with pytest.raises(AdapterError, match="failed"):
            backend.apply_image(tmp_path / "w.png")

    def test_no_tool_reports_accurately(self, tmp_path):
        backend = WallpaperBackend(tools={}, runner=FakeRunner())
        with pytest.raises(AdapterError, match="plasma-apply-wallpaperimage"):
            backend.apply_image(tmp_path / "w.png")

    def test_fill_mode_forwarded(self, tmp_path):
        runner = FakeRunner()
        backend = WallpaperBackend(tools=_tools(), runner=runner)
        backend.apply_image(tmp_path / "w.png", fill_mode="preserveAspectCrop")
        assert "-f" in runner.calls[0]
        assert "preserveAspectCrop" in runner.calls[0]


class TestBackendReadBack:
    def test_current_images_from_qdbus_script(self):
        runner = FakeRunner(lambda argv: FakeProc(0, SCRIPT_LINE + "\n", ""))
        backend = WallpaperBackend(tools=_tools(), runner=runner)
        images = backend.current_images()
        assert images == ["file:///wallpapers/one.png"]
        call = runner.calls[0]
        assert call[0] == "/usr/bin/qdbus6"
        assert "org.kde.PlasmaShell.evaluateScript" in call
        script = call[-1]
        assert 'currentConfigGroup=["Wallpaper","org.kde.image","General"]' in script

    def test_appletsrc_fallback_when_no_qdbus(self, tmp_path):
        appletsrc = tmp_path / "plasma-org.kde.plasma.desktop-appletsrc"
        appletsrc.write_text(
            "[Containments][1]\nItemGeometriesHorizontal=\n\n"
            "[Containments][1][Wallpaper][org.kde.image][General]\n"
            "Image=file:///imgs/first.png\n"
            "FillMode=2\n\n"
            "[Containments][2][Wallpaper][other.plugin][General]\n"
            "Image=file:///imgs/ignored.png\n\n"
            "[Containments][3][Wallpaper][org.kde.image][General]\n"
            "Image=file:///imgs/second.png\n"
        )
        backend = WallpaperBackend(tools=_tools(qdbus6=None),
                                   runner=FakeRunner(),
                                   appletsrc_path=appletsrc)
        assert backend.current_images() == [
            "file:///imgs/first.png",
            "file:///imgs/second.png",
        ]

    def test_read_back_prefers_live_query_over_appletsrc(self, tmp_path):
        appletsrc = tmp_path / "appletsrc"
        appletsrc.write_text(
            "[Containments][9][Wallpaper][org.kde.image][General]\n"
            "Image=file:///stale.png\n"
        )
        runner = FakeRunner(lambda argv: FakeProc(0, "0|file:///live.png\n", ""))
        backend = WallpaperBackend(tools=_tools(), runner=runner,
                                   appletsrc_path=appletsrc)
        assert backend.current_images() == ["file:///live.png"]

    def test_script_null_values_skipped(self):
        urls = WallpaperBackend._parse_script_output("0|\n1|null\n2|file:///ok.png\n")
        assert urls == ["file:///ok.png"]

    def test_unreadable_everything_returns_empty(self, tmp_path):
        backend = WallpaperBackend(tools={}, runner=FakeRunner(),
                                   appletsrc_path=tmp_path / "absent")
        assert backend.current_images() == []
