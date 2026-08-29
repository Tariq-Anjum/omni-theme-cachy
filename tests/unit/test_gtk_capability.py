"""Unit tests for structured GTK capability classification (session 11).

Covers the session's required cases at the capability level: no GTK,
GTK present, KDE GTK sync present (both signals), non-Breeze GTK
theme, and repeat detection. Detection is hermetic: it probes a
sandbox config home with an injected ``which`` and must never write.
"""

from __future__ import annotations

from pathlib import Path

from adapters.gtk.capability import (
    MODE_DIRECT,
    MODE_KDE_NATIVE_SYNC,
    MODE_UNSUPPORTED,
    detect_capability,
    doctor_report,
    is_breeze,
    mode_of,
)
from adapters.gtk.detection import detect_gtk

KCM = "/usr/bin/kcmshell6"

REQUIRED_DOCTOR_KEYS = {"adapter", "supported", "mode", "gtk3", "gtk4", "notes"}


def _detect(config_home: Path, *, versions=("gtk-3.0",), settings="",
            kcmshell6: str | None = None):
    config_home.mkdir(parents=True, exist_ok=True)
    for version in versions:
        d = config_home / version
        d.mkdir(parents=True, exist_ok=True)
        if settings:
            (d / "settings.ini").write_text(settings)
    return detect_gtk(
        env={"XDG_CURRENT_DESKTOP": "KDE"},
        which=(
            (lambda name: KCM if name == "kcmshell6" else None)
            if kcmshell6 else (lambda name: None)
        ),
        config_home=config_home,
    )


class TestNoGTK:
    def test_capability_is_unsupported_with_documented_reason(self, tmp_path):
        cap = detect_capability(_detect(tmp_path / "cfg", versions=()))
        assert mode_of(cap) == MODE_UNSUPPORTED
        assert cap.kde_gtk_sync_detected is False
        assert cap.reason and "no GTK configuration" in cap.reason

    def test_doctor_reports_accurate_unsupported_result(self, tmp_path):
        env = _detect(tmp_path / "cfg", versions=())
        report = doctor_report(env, detect_capability(env))
        assert REQUIRED_DOCTOR_KEYS <= set(report)
        assert report["adapter"] == "gtk"
        assert report["supported"] is False
        assert report["mode"] == MODE_UNSUPPORTED
        assert report["gtk3"] is False and report["gtk4"] is False
        assert report["notes"] and "no GTK configuration" in report["notes"][0]


class TestGTKPresent:
    def test_gtk3_without_sync_is_directly_supported(self, tmp_path):
        cap = detect_capability(_detect(tmp_path / "cfg"))
        assert cap.gtk3_detected is True and cap.gtk4_detected is False
        assert cap.kde_gtk_sync_detected is False
        assert cap.direct_css_supported is True
        assert mode_of(cap) == MODE_DIRECT
        assert cap.reason is None

    def test_doctor_notes_direct_is_opt_in(self, tmp_path):
        env = _detect(tmp_path / "cfg")
        report = doctor_report(env, detect_capability(env))
        assert report["supported"] is True
        assert report["mode"] == MODE_DIRECT
        assert any("opt-in" in note for note in report["notes"])

    def test_sync_presence_disables_direct_css(self, tmp_path):
        env = _detect(tmp_path / "cfg", kcmshell6=KCM)
        cap = detect_capability(env)
        assert cap.direct_css_supported is False


class TestKdeGtkSyncPresent:
    def test_kcmshell6_signal(self, tmp_path):
        cap = detect_capability(_detect(tmp_path / "cfg", kcmshell6=KCM))
        assert cap.kde_gtk_sync_detected is True
        assert mode_of(cap) == MODE_KDE_NATIVE_SYNC
        assert cap.reason is None

    def test_colorreload_module_signal_without_kcmshell6(self, tmp_path):
        ini = "[Settings]\ngtk-modules=colorreload-gtk-module\n"
        cap = detect_capability(_detect(tmp_path / "cfg", settings=ini))
        assert cap.kde_gtk_sync_detected is True
        assert mode_of(cap) == MODE_KDE_NATIVE_SYNC

    def test_gtk4_only_with_sync_is_supported(self, tmp_path):
        cap = detect_capability(
            _detect(tmp_path / "cfg", versions=("gtk-4.0",), kcmshell6=KCM)
        )
        assert cap.gtk4_detected is True and cap.gtk3_detected is False
        assert mode_of(cap) == MODE_KDE_NATIVE_SYNC


class TestNonBreezeBoundary:
    def test_breeze_variants_detected(self):
        assert is_breeze("breeze") is True
        assert is_breeze("BreezeDark") is True
        assert is_breeze("breeze-light") is True

    def test_non_breeze_theme_recorded(self, tmp_path):
        ini = "[Settings]\ngtk-theme-name=WhiteSur-Light\n"
        env = _detect(tmp_path / "cfg", settings=ini, kcmshell6=KCM)
        cap = detect_capability(env)
        assert cap.breeze_gtk_detected is False
        assert cap.kde_gtk_sync_detected is True
        # The mechanism is present, so the mode stays kde-native-sync;
        # the boundary is reported as a note, not a mode downgrade.
        report = doctor_report(env, cap)
        assert report["mode"] == MODE_KDE_NATIVE_SYNC
        assert any("WhiteSur-Light" in n and "not Breeze" in n
                   for n in report["notes"])

    def test_no_theme_name_claimed_nothing(self, tmp_path):
        env = _detect(tmp_path / "cfg", kcmshell6=KCM)
        cap = detect_capability(env)
        assert cap.breeze_gtk_detected is False
        assert all("not Breeze" not in n
                   for n in doctor_report(env, cap)["notes"])

    def test_breeze_theme_yields_no_boundary_notes(self, tmp_path):
        ini = "[Settings]\ngtk-theme-name=Breeze\n"
        env = _detect(tmp_path / "cfg", settings=ini, kcmshell6=KCM)
        (env.config_home / "gtk-3.0" / "colors.css").write_text(
            "@define-color theme_bg_color_breeze #14161c;\n"
        )
        report = doctor_report(env, detect_capability(env))
        assert report["notes"] == []


class TestGTK4OnlyWithoutSync:
    def test_unsupported_with_libadwaita_reason(self, tmp_path):
        cap = detect_capability(_detect(tmp_path / "cfg", versions=("gtk-4.0",)))
        assert mode_of(cap) == MODE_UNSUPPORTED
        assert cap.reason and "libadwaita" in cap.reason
        assert cap.direct_css_supported is False


class TestRepeatDetection:
    def test_repeated_detection_is_stable_and_writes_nothing(self, tmp_path):
        cfg = tmp_path / "cfg"
        ini = "[Settings]\ngtk-theme-name=BreezeDark\ngtk-modules=colorreload-gtk-module\n"
        env = _detect(cfg, settings=ini, kcmshell6=KCM)

        before = sorted((str(p), p.stat().st_mtime_ns) for p in cfg.rglob("*"))
        first = detect_capability(env)
        second = detect_capability(detect_gtk(
            env={"XDG_CURRENT_DESKTOP": "KDE"},
            which=lambda name: KCM if name == "kcmshell6" else None,
            config_home=cfg,
        ))
        after = sorted((str(p), p.stat().st_mtime_ns) for p in cfg.rglob("*"))

        assert first == second
        assert mode_of(first) == MODE_KDE_NATIVE_SYNC
        assert before == after
