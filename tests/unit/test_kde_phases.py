"""Hermetic unit tests for the KDE adapter contract phases.

Runs on machines without KDE: environment, binaries and process output
are injected through the adapter's seams. Every filesystem-touching
test uses the ``fake_home`` fixture so the real user's
``~/.local/share/color-schemes`` is never touched.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.activation import ActivationContext  # noqa: E402
from core.errors import AdapterError  # noqa: E402
from core.events import EVENT_POST_ACTIVATE, EventDispatcher  # noqa: E402
from core.staging import Manifest, ManifestFileEntry  # noqa: E402
from core.state import RuntimeState  # noqa: E402
from core.theme_loader import load_theme  # noqa: E402

from adapters.kde.adapter import KdeAdapter  # noqa: E402
from adapters.kde.config import SCHEME_ID, journal_path, scheme_file_path  # noqa: E402
from adapters.kde.wallpaper import Journal  # noqa: E402
from tests.conftest import write_theme  # noqa: E402

PNG_MAGIC = b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR"

KDE_ENV = {"XDG_CURRENT_DESKTOP": "KDE", "XDG_SESSION_TYPE": "wayland"}

TOOLS = {
    name: f"/usr/bin/{name}"
    for name in (
        "plasma-apply-colorscheme",
        "plasma-apply-wallpaperimage",
        "kreadconfig6",
        "qdbus6",
        "plasmashell",
    )
}


@dataclass
class FakeProc:
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


class FakeRunner:
    def __init__(self, script=None):
        self.calls: list[list[str]] = []
        self.script = script or (lambda argv: FakeProc(0, "", ""))

    def __call__(self, argv):
        self.calls.append(list(argv))
        return self.script(argv)


def _which_factory(tools):
    return lambda name: tools.get(name)


def _make_adapter(**kwargs) -> KdeAdapter:
    defaults = dict(
        env=KDE_ENV,
        which=_which_factory(TOOLS),
        runner=FakeRunner(),
        version_runner=lambda argv: "plasmashell 6.7.4",
    )
    defaults.update(kwargs)
    return KdeAdapter(**defaults)


def _manifest_with_scheme(scheme_path: Path) -> Manifest:
    entry = ManifestFileEntry(
        name="kde/OmniTheme.colors.tpl",
        source="templates/kde/OmniTheme.colors.tpl",
        origin="builtin",
        target=str(scheme_path),
        adapter="kde-colorscheme",
        hash="0" * 64,
        staged="kde/OmniTheme.colors",
    )
    return Manifest(
        theme_name="Test", theme_id="test", theme_version=1, mode="dark",
        theme_source=Path("."), timestamp="now", ownership="base",
        files=(entry,),
    )


def _empty_manifest() -> Manifest:
    return Manifest(
        theme_name="t", theme_id="t", theme_version=1, mode="dark",
        theme_source=Path("."), timestamp="now", ownership="base", files=(),
    )


def _context(tmp_path: Path, manifest: Manifest, theme) -> ActivationContext:
    generation = tmp_path / "generation"
    generation.mkdir(parents=True, exist_ok=True)
    for entry in manifest.files:
        artifact = generation / entry.staged
        artifact.parent.mkdir(parents=True, exist_ok=True)
        if not artifact.exists():
            artifact.write_text("[General]\nColorScheme=placeholder\n")
    return ActivationContext(
        state_root=tmp_path / "state",
        generation_dir=generation,
        manifest=manifest,
        theme=theme,
        dry_run=False,
        previous_state=RuntimeState(),
    )


def _install_scheme(content: str) -> Path:
    path = scheme_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


@pytest.fixture
def kde_theme(tmp_path):
    """Theme fixture with an existing wallpaper image."""
    theme_dir = write_theme(tmp_path / "theme")
    wall = theme_dir / "wallpapers"
    wall.mkdir(exist_ok=True)
    (wall / "test.png").write_bytes(PNG_MAGIC)
    return load_theme(theme_dir)


class TestCapability:
    def test_supported_on_plasma6(self):
        cap = _make_adapter().capability(None)
        assert cap.supported
        assert cap.version == "6.7.4"

    def test_unsupported_without_kde(self):
        adapter = _make_adapter(
            env={"XDG_CURRENT_DESKTOP": "GNOME"},
            which=_which_factory({}),
            version_runner=lambda argv: None,
        )
        cap = adapter.capability(None)
        assert not cap.supported
        assert "no KDE Plasma session" in cap.reason

    def test_unsupported_when_tools_missing(self):
        adapter = _make_adapter(
            env=KDE_ENV,
            which=_which_factory({"plasmashell": "/usr/bin/plasmashell"}),
            version_runner=lambda argv: "plasmashell 6.7.4",
        )
        cap = adapter.capability(None)
        assert not cap.supported
        assert "missing required tools" in cap.reason


class TestPlan:
    def test_plan_detects_managed_scheme_target(self, tmp_path, kde_theme):
        adapter = _make_adapter()
        ctx = _context(tmp_path, _manifest_with_scheme(scheme_file_path()), kde_theme)
        plan = adapter.plan(kde_theme, ctx)
        assert plan.scheme_id == SCHEME_ID
        assert plan.scheme_managed_by_core
        assert plan.scheme_path == scheme_file_path()

    def test_plan_flags_unmanaged_scheme(self, tmp_path, kde_theme):
        adapter = _make_adapter()
        ctx = _context(tmp_path, _empty_manifest(), kde_theme)
        plan = adapter.plan(kde_theme, ctx)
        assert not plan.scheme_managed_by_core

    def test_plan_predicts_cache_path_without_copying(self, tmp_path, kde_theme):
        adapter = _make_adapter()
        ctx = _context(tmp_path, _manifest_with_scheme(scheme_file_path()), kde_theme)
        plan = adapter.plan(kde_theme, ctx)
        assert plan.wallpaper_source == kde_theme.resolve_wallpaper()
        assert plan.wallpaper_cache is not None
        assert not plan.wallpaper_cache.exists(), "plan must not copy anything"
        assert plan.wallpaper_cache.parent == (
            (tmp_path / "state") / "adapters" / "wallpaper-cache"
        )
        modes = {r.surface: r.mode for r in plan.surface_report}
        assert modes["popups.background"] == "direct"
        assert modes["controls.normal-border"] == "unsupported"

    def test_plan_warns_on_missing_wallpaper(self, tmp_path):
        theme_dir = write_theme(tmp_path / "theme")  # no wallpaper on disk
        theme = load_theme(theme_dir)
        adapter = _make_adapter()
        ctx = _context(tmp_path, _manifest_with_scheme(scheme_file_path()), theme)
        plan = adapter.plan(theme, ctx)
        assert plan.wallpaper_cache is None
        assert any("missing on disk" in w for w in plan.warnings)

    def test_plan_is_read_only(self, tmp_path, kde_theme):
        adapter = _make_adapter()
        ctx = _context(tmp_path, _manifest_with_scheme(scheme_file_path()), kde_theme)
        before = sorted(str(p) for p in ctx.state_root.rglob("*"))
        adapter.plan(kde_theme, ctx)
        after = sorted(str(p) for p in ctx.state_root.rglob("*"))
        assert before == after


class TestRender:
    def test_render_accepts_present_artifact(self, tmp_path, kde_theme):
        adapter = _make_adapter()
        ctx = _context(tmp_path, _manifest_with_scheme(scheme_file_path()), kde_theme)
        adapter.render(kde_theme, ctx.generation_dir, ctx)  # must not raise

    def test_render_raises_on_missing_artifact(self, tmp_path, kde_theme):
        adapter = _make_adapter()
        ctx = _context(tmp_path, _manifest_with_scheme(scheme_file_path()), kde_theme)
        (ctx.generation_dir / "kde" / "OmniTheme.colors").unlink()
        with pytest.raises(AdapterError, match="missing from generation"):
            adapter.render(kde_theme, ctx.generation_dir, ctx)


class TestApply:
    def test_apply_runs_native_colorscheme_tool(self, tmp_path, fake_home,
                                                 kde_theme):
        runner = FakeRunner()
        adapter = _make_adapter(runner=runner)
        ctx = _context(tmp_path, _manifest_with_scheme(scheme_file_path()), kde_theme)
        _install_scheme("[General]\nColorScheme=OmniTheme\n")

        result = adapter.apply(adapter.plan(kde_theme, ctx), ctx)

        assert result.applied and not result.errors
        colorscheme_calls = [
            c for c in runner.calls if c[0] == "/usr/bin/plasma-apply-colorscheme"
        ]
        assert colorscheme_calls == [["/usr/bin/plasma-apply-colorscheme", SCHEME_ID]]

    def test_apply_reports_colorscheme_failure(self, tmp_path, fake_home,
                                               kde_theme):
        def script(argv):
            if "colorscheme" in argv[0]:
                return FakeProc(1, "", "Unknown color scheme")
            return FakeProc(0, "", "")

        adapter = _make_adapter(runner=FakeRunner(script))
        ctx = _context(tmp_path, _manifest_with_scheme(scheme_file_path()), kde_theme)
        _install_scheme("x")
        result = adapter.apply(adapter.plan(kde_theme, ctx), ctx)
        assert not result.applied
        assert any("plasma-apply-colorscheme" in e for e in result.errors)

    def test_apply_journals_previous_wallpaper(self, tmp_path, fake_home,
                                               kde_theme):
        runner = FakeRunner(
            lambda argv: FakeProc(0, "0|file:///home/u/orig.png\n", "")
        )
        adapter = _make_adapter(runner=runner)
        ctx = _context(tmp_path, _manifest_with_scheme(scheme_file_path()), kde_theme)
        _install_scheme("x")

        plan = adapter.plan(kde_theme, ctx)
        result = adapter.apply(plan, ctx)

        assert result.applied
        saved = Journal.load(journal_path(ctx.state_root))
        assert saved.pre_omni_wallpaper == "file:///home/u/orig.png"
        assert saved.history["test"] == str(plan.wallpaper_cache)

    def test_apply_preserves_first_known_previous(self, tmp_path, fake_home,
                                                  kde_theme):
        """A later apply must not overwrite the true pre-Omni wallpaper."""
        runner = FakeRunner(lambda argv: FakeProc(0, "0|file:///now-omni.png\n", ""))
        adapter = _make_adapter(runner=runner)
        ctx = _context(tmp_path, _manifest_with_scheme(scheme_file_path()), kde_theme)
        _install_scheme("x")

        record = journal_path(ctx.state_root)
        record.parent.mkdir(parents=True)
        record.write_text(
            '{"version": 2, "pre_omni_wallpaper": "file:///the-original.png",'
            ' "history": {}}'
        )

        adapter.apply(adapter.plan(kde_theme, ctx), ctx)
        saved = Journal.load(record)
        assert saved.pre_omni_wallpaper == "file:///the-original.png"

    def test_apply_without_wallpaper_still_succeeds(self, tmp_path, fake_home):
        theme_dir = write_theme(tmp_path / "plain")  # no wallpapers/
        theme = load_theme(theme_dir)
        adapter = _make_adapter()
        ctx = _context(tmp_path, _manifest_with_scheme(scheme_file_path()), theme)
        _install_scheme("x")
        result = adapter.apply(adapter.plan(theme, ctx), ctx)
        assert result.applied and not result.errors


class TestVerify:
    def _setup(self, tmp_path, kde_theme, runner=None):
        adapter = _make_adapter(runner=runner)
        ctx = _context(tmp_path, _manifest_with_scheme(scheme_file_path()), kde_theme)
        _install_scheme("[General]\nName=Omni Theme\nColorScheme=OmniTheme\n")
        return adapter, ctx

    def test_verify_detects_wrong_selection_in_kdeglobals(self, tmp_path, fake_home,
                                                          kde_theme):
        runner = FakeRunner(lambda argv: FakeProc(0, "SomethingElse\n", ""))
        adapter, ctx = self._setup(tmp_path, kde_theme, runner)
        result = adapter.verify(adapter.plan(kde_theme, ctx), ctx)
        assert not result.verified
        assert any("did not take effect" in e for e in result.errors)

    def test_verify_detects_tampered_scheme_file(self, tmp_path, fake_home,
                                                 kde_theme):
        def script(argv):
            if "kreadconfig6" in argv[0]:
                return FakeProc(0, f"{SCHEME_ID}\n", "")
            return FakeProc(0, "", "")

        adapter, ctx = self._setup(tmp_path, kde_theme, FakeRunner(script))
        plan = adapter.plan(kde_theme, ctx)
        # overwrite installed file with content that disagrees with model
        scheme_file_path().write_text(
            "[General]\nName=Omni Theme\nColorScheme=OmniTheme\n"
            "[Colors:Window]\nBackgroundNormal=9,9,9\n"
        )
        result = adapter.verify(plan, ctx)
        assert not result.verified
        assert any("[Colors:Window]" in e for e in result.errors)

    def test_verify_requires_live_wallpaper_match(self, tmp_path, fake_home,
                                                  kde_theme):
        def script(argv):
            if "kreadconfig6" in argv[0]:
                return FakeProc(0, f"{SCHEME_ID}\n", "")
            if "qdbus6" in argv[0]:
                return FakeProc(0, "0|file:///somewhere/else.png\n", "")
            return FakeProc(0, "", "")

        adapter, ctx = self._setup(tmp_path, kde_theme, FakeRunner(script))
        result = adapter.verify(adapter.plan(kde_theme, ctx), ctx)
        assert not result.verified
        assert any("wallpaper" in e.lower() for e in result.errors)

    def test_verify_passes_when_everything_matches(self, tmp_path, fake_home):
        # surface-less theme: builtin template output must satisfy the
        # derived-elevation model exactly.
        theme_dir = write_theme(tmp_path / "bare", surfaces=None)
        wall = theme_dir / "wallpapers"
        wall.mkdir(exist_ok=True)
        (wall / "test.png").write_bytes(PNG_MAGIC)
        theme = load_theme(theme_dir)

        def script(argv):
            if "kreadconfig6" in argv[0]:
                return FakeProc(0, f"{SCHEME_ID}\n", "")
            return FakeProc(0, "", "")

        adapter = _make_adapter(runner=FakeRunner(script))
        ctx = _context(tmp_path, _manifest_with_scheme(scheme_file_path()), theme)
        plan = adapter.plan(theme, ctx)
        from core.renderer import render_template_file, resolve_template

        resolved = resolve_template(
            "kde/OmniTheme.colors.tpl",
            theme_dir=theme_dir,
            builtin_root=PROJECT_ROOT / "templates",
        )
        assert resolved.origin == "builtin"
        _install_scheme(render_template_file(resolved.path, theme))
        uri = plan.wallpaper_cache.resolve().as_uri()

        def with_wallpaper(argv):
            if "qdbus6" in argv[0]:
                return FakeProc(0, f"0|{uri}\n", "")
            return script(argv)

        adapter2 = _make_adapter(runner=FakeRunner(with_wallpaper))
        result = adapter2.verify(plan, ctx)
        assert result.verified, result.errors


class TestRollback:
    def test_rollback_reapplies_and_restores_theme_wallpaper(self, tmp_path,
                                                             fake_home,
                                                             kde_theme):
        """Rolling back to a generation of theme T restores T's wallpaper."""
        calls: list[list[str]] = []

        def script(argv):
            calls.append(list(argv))
            if "qdbus6" in argv[0]:
                return FakeProc(0, "0|file:///cached/by-omni.png\n", "")
            return FakeProc(0, "", "")

        adapter = _make_adapter(runner=FakeRunner(script))
        # manifest of the generation being restored (theme "test")
        ctx = _context(tmp_path, _manifest_with_scheme(scheme_file_path()), kde_theme)
        record = journal_path(ctx.state_root)
        record.parent.mkdir(parents=True)
        record.write_text(
            '{"version": 2,'
            ' "pre_omni_wallpaper": "file:///home/u/orig.png",'
            ' "history": {"test": "/cache/test-wall.png"}}'
        )

        result = adapter.rollback(None, ctx)

        assert result.rolled_back and not result.errors
        reapplied = [c for c in calls if c[0].endswith("plasma-apply-colorscheme")]
        assert reapplied[-1][1] == SCHEME_ID
        restored = [c for c in calls if c[0].endswith("plasma-apply-wallpaperimage")]
        assert restored and restored[-1][1] == "/cache/test-wall.png"

    def test_rollback_falls_back_to_pre_omni_wallpaper(self, tmp_path,
                                                       fake_home, kde_theme):
        calls: list[list[str]] = []

        def script(argv):
            calls.append(list(argv))
            return FakeProc(0, "", "")

        adapter = _make_adapter(runner=FakeRunner(script))
        ctx = _context(tmp_path, _manifest_with_scheme(scheme_file_path()), kde_theme)
        record = journal_path(ctx.state_root)
        record.parent.mkdir(parents=True)
        record.write_text(
            '{"version": 2,'
            ' "pre_omni_wallpaper": "file:///home/u/orig.png",'
            ' "history": {"other-theme": "/cache/other.png"}}'
        )
        result = adapter.rollback(None, ctx)
        restored = [c for c in calls if c[0].endswith("plasma-apply-wallpaperimage")]
        assert restored and restored[-1][1] == "/home/u/orig.png"
        assert result.rolled_back

    def test_rollback_without_journal_only_reapplies_scheme(self, tmp_path,
                                                            fake_home,
                                                            kde_theme):
        runner = FakeRunner()
        adapter = _make_adapter(runner=runner)
        ctx = _context(tmp_path, _manifest_with_scheme(scheme_file_path()), kde_theme)
        result = adapter.rollback(None, ctx)
        assert result.rolled_back
        assert [c for c in runner.calls if "wallpaperimage" in c[0]] == []

    def test_rollback_warns_when_previous_was_not_plain_image(self, tmp_path,
                                                              fake_home,
                                                              kde_theme):
        adapter = _make_adapter()
        ctx = _context(tmp_path, _manifest_with_scheme(scheme_file_path()), kde_theme)
        record = journal_path(ctx.state_root)
        record.parent.mkdir(parents=True)
        record.write_text(
            '{"version": 2,'
            ' "pre_omni_wallpaper": "https://example.com/x.png",'
            ' "history": {}}'
        )
        result = adapter.rollback(None, ctx)
        assert result.rolled_back
        assert any("not a local image" in w for w in result.warnings)


class TestEventSubscription:
    def test_registry_forwards_events_to_adapter(self):
        from core.adapters import AdapterRegistry

        received = []

        class Listening(KdeAdapter):
            def on_event(self, event):
                received.append(event.name)

        registry = AdapterRegistry()
        registry.register(Listening(env={}, which=_which_factory({})))
        dispatcher = EventDispatcher()
        registry.attach(dispatcher)
        dispatcher.emit(EVENT_POST_ACTIVATE)
        assert received == ["post_activate"]
