"""Integration tests against a real KDE Plasma 6 session (marked ``kde``).

Safety contract
---------------
These tests never alter the live desktop:

* no ``plasma-apply-colorscheme`` / wallpaper tool is invoked;
* staging runs inside a temporary state root;
* only read-only probes touch the session (detection, wallpaper
  read-back, kdeglobals *reads*).

The destructive end-to-end path (apply → verify → rollback on the real
desktop) is exercised manually via the CLI; see
docs/architecture/KDE_ADAPTER.md ("Real-machine verification matrix").
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.engine import ThemeEngine  # noqa: E402
from core.theme_loader import load_theme  # noqa: E402

from adapters import build_default_registry  # noqa: E402
from adapters import kde as kde_pkg  # noqa: E402
from adapters.kde.adapter import KdeAdapter  # noqa: E402
from adapters.kde.config import SCHEME_ID, scheme_file_path  # noqa: E402

pytestmark = [
    pytest.mark.kde,
]

_adapter = KdeAdapter()
_env = _adapter.environment()

requires_plasma6 = pytest.mark.skipif(
    not (_env.is_plasma_session or _env.plasmashell_version),
    reason="not a KDE Plasma session",
)

SHIPPED_THEME = PROJECT_ROOT / "themes" / "default"


@requires_plasma6
class TestLiveDetection:
    def test_plasma_version_is_6(self):
        env = _env
        assert env.is_plasma_session, f"desktop={env.desktop!r}"
        assert env.major_version == 6, env.plasmashell_version

    def test_required_native_tools_installed(self):
        assert _env.has("plasma-apply-colorscheme")
        assert _env.has("kreadconfig6")

    def test_adapter_capability_supported(self):
        cap = _adapter.capability(None)
        assert cap.supported
        assert cap.id == "kde"


@requires_plasma6
class TestReadOnlySessionProbes:
    def test_wallpaper_read_back_works(self):
        backend = _adapter._backend()
        if not backend.can_read_back():
            pytest.skip("neither qdbus6 nor appletsrc readable")
        images = backend.current_images()
        assert isinstance(images, list)
        for url in images:
            assert "://" in url  # URI-shaped

    def test_kdeglobals_readable_without_modification(self):
        import subprocess

        proc = subprocess.run(
            ["kreadconfig6", "--file", "kdeglobals",
             "--group", "General", "--key", "ColorScheme"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        assert proc.returncode == 0
        current = proc.stdout.strip()
        # Whatever the user runs today, reading it must not change it.
        assert current  # a scheme name exists


@requires_plasma6
class TestStagingToPlan:
    """Full render pipeline into an isolated state root; no live writes."""

    def make_engine(self, tmp_path: Path) -> ThemeEngine:
        return ThemeEngine(
            themes_root=PROJECT_ROOT / "themes",
            templates_root=PROJECT_ROOT / "templates",
            state_root=tmp_path / "state",
            registry_path=PROJECT_ROOT / "templates" / "targets.toml",
            adapters=build_default_registry(),
        )

    def test_dry_run_reports_kde_capability(self, tmp_path):
        engine = self.make_engine(tmp_path)
        outcome = engine.apply("default", dry_run=True)
        assert outcome.status == "DRY_RUN"
        caps = {c.id: c for c in outcome.capabilities}
        assert "kde" in caps
        assert caps["kde"].supported

    def test_staged_scheme_matches_model(self, tmp_path):
        engine = self.make_engine(tmp_path)
        outcome = engine.apply("default", dry_run=True)
        assert outcome.status == "DRY_RUN"

        from core.staging import stage_theme

        staged = stage_theme(
            SHIPPED_THEME,
            registry_path=engine.registry_path,
            templates_root=engine.templates_root,
            state_root=tmp_path / "state",
        )
        scheme_entries = [f for f in staged.files if f.name.endswith("OmniTheme.colors.tpl")]
        assert len(scheme_entries) == 1
        artifact = staged.staging_dir / scheme_entries[0].staged
        text = artifact.read_text(encoding="utf-8")

        theme = load_theme(SHIPPED_THEME)
        from adapters.kde import colors as kc

        problems = kc.verify_scheme_text(
            text, dict(theme.palette.colors), dict(theme.surfaces.items())
        )
        assert problems == []
        parsed = kc.parse_scheme_text(text)
        assert parsed[("General", "ColorScheme")] == SCHEME_ID

    def test_plan_against_real_environment(self, tmp_path):
        engine = self.make_engine(tmp_path)
        from core.activation import ActivationContext, activate  # noqa: F401
        from core.state import RuntimeState
        from core.staging import load_manifest, stage_theme

        assert engine.apply("default", dry_run=True).status == "DRY_RUN"

        theme = load_theme(SHIPPED_THEME)
        adapter = KdeAdapter()

        staged = stage_theme(
            SHIPPED_THEME,
            registry_path=engine.registry_path,
            templates_root=engine.templates_root,
            state_root=tmp_path / "state",
        )
        manifest = load_manifest(staged.manifest_path)
        ctx = ActivationContext(
            state_root=tmp_path / "state",
            generation_dir=staged.staging_dir,
            manifest=manifest,
            theme=theme,
            dry_run=True,
            previous_state=RuntimeState(),
        )
        existed_before = scheme_file_path().exists()
        plan = adapter.plan(theme, ctx)
        report = plan.to_dict()
        assert report["scheme_managed_by_core"] is True
        modes = {r["surface"]: r["mode"] for r in report["surface_report"]}
        assert modes["popups.background"] in ("direct", "derived")
        # plan must not have installed anything live
        assert scheme_file_path().exists() == existed_before
