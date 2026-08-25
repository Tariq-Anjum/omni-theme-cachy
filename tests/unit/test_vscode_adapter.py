"""Unit tests for the VS Code adapter (session 06).

Hermetic: no VS Code installation is required. The adapter's config
home is pointed at a sandbox and every filesystem-touching test runs
inside it. Coverage follows the session-08 matrix: empty configuration,
existing user configuration (comments!), unrelated settings, malformed
JSON, repeated application, rollback, missing application, unsupported
configuration, path traversal, user-modification conflicts.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.errors import AdapterError
from core.theme_loader import load_theme

from adapters.vscode import jsonc as vjson
from adapters.vscode.adapter import (
    APP_DIRS,
    Journal,
    VscodeAdapter,
    discover_settings_file,
    journal_path,
)
from adapters.vscode.mapping import COLOR_CUSTOMIZATIONS_KEY


def _theme(make_theme):
    """A fully loaded Theme object built from a fresh fixture theme dir."""
    return load_theme(make_theme())


def _user_dir(config_home: Path, app: str = "Code") -> Path:
    d = config_home / app / "User"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _adapter(config_home: Path) -> VscodeAdapter:
    return VscodeAdapter(config_home=config_home)


def _run(adapter, theme, ctx):
    plan = adapter.plan(theme, ctx)
    applied = adapter.apply(plan, ctx)
    verified = adapter.verify(plan, ctx)
    return plan, applied, verified


class TestDiscovery:
    def test_discovery_none_without_installation(self, tmp_path):
        assert discover_settings_file(tmp_path) is None

    def test_prefers_code_then_oss_then_vscodium(self, tmp_path):
        assert discover_settings_file(tmp_path) is None
        oss = _user_dir(tmp_path, "Code - OSS")
        assert discover_settings_file(tmp_path) == oss / "settings.json"
        code = _user_dir(tmp_path, "Code")
        assert discover_settings_file(tmp_path) == code / "settings.json"

    def test_app_dirs_cover_family(self):
        assert set(APP_DIRS) >= {"Code", "VSCodium"}


class TestCapability:
    def test_unsupported_when_not_installed(self, tmp_path):
        cap = _adapter(tmp_path).capability(None)
        assert cap.supported is False
        assert "not installed" in cap.reason

    def test_unsupported_reason_mentions_user_dir(self, tmp_path):
        (tmp_path / "VSCodium").mkdir()
        cap = _adapter(tmp_path).capability(None)
        assert cap.supported is False
        assert "User directory" in cap.reason

    def test_supported_with_empty_user_dir(self, tmp_path):
        _user_dir(tmp_path)
        assert _adapter(tmp_path).capability(None).supported is True


class TestApplyEmptyConfiguration:
    def test_creates_settings_from_nothing(self, tmp_path, make_theme, context_factory):
        user = _user_dir(tmp_path)
        settings = user / "settings.json"
        theme = _theme(make_theme)
        adapter = _adapter(tmp_path)
        plan, applied, verified = _run(
            adapter, theme, context_factory(theme=theme)
        )

        assert applied.applied is True
        assert verified.verified is True
        data = json.loads(settings.read_text())
        assert data[COLOR_CUSTOMIZATIONS_KEY]["editor.background"] == "#14161c"
        # terminal ANSI ramp mapped onto documented keys
        term = {k: v for k, v in data[COLOR_CUSTOMIZATIONS_KEY].items()
                if k.startswith("terminal.ansi")}
        assert len(term) == 16


class TestExistingConfigurationPreserved:
    def test_comments_and_unrelated_settings_survive_byte_level(
        self, tmp_path, make_theme, context_factory
    ):
        user = _user_dir(tmp_path)
        settings = user / "settings.json"
        original = (
            '{\n'
            '  // my editor prefs, do not touch\n'
            '  "editor.fontSize": 14,\n'
            '  "editor.rulers": [80], /* column guide */\n'
            '  "git.enableSmartCommit": true,\n'
            '}\n'
        )
        settings.write_text(original)

        adapter = _adapter(tmp_path)
        theme = _theme(make_theme)
        plan, applied, verified = _run(adapter, theme, context_factory(theme=theme))

        assert applied.applied and verified.verified
        new_text = settings.read_text()
        # comments preserved verbatim
        assert "// my editor prefs, do not touch" in new_text
        assert "/* column guide */" in new_text
        # unrelated settings preserved with their values
        data = vjson.loads(new_text)
        assert data["editor.fontSize"] == 14
        assert data["editor.rulers"] == [80]
        assert data["git.enableSmartCommit"] is True
        # managed colors present
        assert data[COLOR_CUSTOMIZATIONS_KEY]["focusBorder"] == "#4f9eea"


class TestMergeWithExistingCustomizations:
    def test_unknown_user_keys_inside_customizations_are_kept(
        self, tmp_path, make_theme, context_factory
    ):
        user = _user_dir(tmp_path)
        settings = user / "settings.json"
        settings.write_text(json.dumps({
            COLOR_CUSTOMIZATIONS_KEY: {
                "statusBar.background": "#ff00ff",  # user's own key
                "editor.background": "#000000",
            },
            "window.zoomLevel": 2,
        }, indent=4))

        adapter = _adapter(tmp_path)
        theme = _theme(make_theme)
        plan, applied, verified = _run(adapter, theme, context_factory(theme=theme))

        assert applied.applied and verified.verified
        data = vjson.loads(settings.read_text())
        custom = data[COLOR_CUSTOMIZATIONS_KEY]
        assert custom["statusBar.background"] == "#ff00ff"
        assert custom["editor.background"] == "#14161c"
        assert data["window.zoomLevel"] == 2

    def test_user_modified_managed_key_is_replaced_with_warning(
        self, tmp_path, make_theme, context_factory
    ):
        """Conflict policy: our keys win, but the takeover is reported."""
        user = _user_dir(tmp_path)
        settings = user / "settings.json"
        settings.write_text(json.dumps({
            COLOR_CUSTOMIZATIONS_KEY: {"focusBorder": "#123456"},
        }))

        adapter = _adapter(tmp_path)
        theme = _theme(make_theme)
        plan, applied, _ = _run(adapter, theme, context_factory(theme=theme))

        warnings = " ".join(applied.warnings)
        assert "focusBorder" in warnings
        assert "#123456" in warnings
        # journal captured the pre-Omni value for exact rollback
        journal = Journal.load(journal_path(context_factory().state_root))
        assert journal.previous_values.get("focusBorder") == "#123456"


class TestMalformedInput:
    def test_malformed_json_refuses_to_write_and_leaves_bytes_alone(
        self, tmp_path, make_theme, context_factory
    ):
        user = _user_dir(tmp_path)
        settings = user / "settings.json"
        broken = '{"editor.fontSize": 14,,,'  # not valid JSONC
        settings.write_text(broken)

        adapter = _adapter(tmp_path)
        theme = _theme(make_theme)
        plan, applied, _ = _run(adapter, theme, context_factory(theme=theme))

        assert applied.errors
        assert not applied.applied
        assert settings.read_text() == broken

    def test_trailing_commas_are_tolerated(self, tmp_path):
        text = '{"a": 1,}'
        assert vjson.loads(text) == {"a": 1}


class TestRepeatedApplication:
    def test_second_apply_is_idempotent_bytes(self, tmp_path, make_theme, context_factory):
        user = _user_dir(tmp_path)
        settings = user / "settings.json"
        adapter = _adapter(tmp_path)
        theme = _theme(make_theme)
        ctx = context_factory(theme=theme)

        _run(adapter, theme, ctx)
        first = settings.read_text()
        plan2, applied2, verified2 = _run(adapter, theme, ctx)
        second = settings.read_text()

        assert first == second
        assert applied2.applied and verified2.verified
        # no duplicate colorCustomizations property
        assert first.count(COLOR_CUSTOMIZATIONS_KEY) == 1


class TestRollback:
    def test_roundtrip_restores_previous_values_and_removes_added_keys(
        self, tmp_path, make_theme, context_factory
    ):
        user = _user_dir(tmp_path)
        settings = user / "settings.json"
        original = '{\n  "workbench.colorCustomizations": {\n    "focusBorder": "#abcdef"\n  }\n}'
        settings.write_text(original)

        adapter = _adapter(tmp_path)
        theme = _theme(make_theme)
        ctx = context_factory(theme=theme)
        _run(adapter, theme, ctx)
        assert "#14161c" in settings.read_text()

        result = adapter.rollback(None, ctx)
        assert result.rolled_back is True
        restored = settings.read_text()
        assert vjson.loads(restored)[COLOR_CUSTOMIZATIONS_KEY] == {"focusBorder": "#abcdef"}

    def test_rollback_removes_colorcustomizations_we_created(
        self, tmp_path, make_theme, context_factory
    ):
        user = _user_dir(tmp_path)
        settings = user / "settings.json"
        settings.write_text('{"editor.fontSize": 12}')

        adapter = _adapter(tmp_path)
        theme = _theme(make_theme)
        ctx = context_factory(theme=theme)
        _run(adapter, theme, ctx)

        result = adapter.rollback(None, ctx)
        assert result.rolled_back is True
        data = vjson.loads(settings.read_text())
        assert COLOR_CUSTOMIZATIONS_KEY not in data
        assert data["editor.fontSize"] == 12

    def test_rollback_without_journal_warns_but_succeeds(
        self, tmp_path, make_theme, context_factory
    ):
        _user_dir(tmp_path)
        adapter = _adapter(tmp_path)
        ctx = context_factory()
        result = adapter.rollback(None, ctx)
        assert result.rolled_back is True
        assert any("journal" in w for w in result.warnings)


class TestUnsupportedAndMissing:
    def test_missing_application_is_skipped_not_failed(self, tmp_path):
        """Unsupported must not masquerade as failure."""
        from core.adapters import AdapterResult

        adapter = _adapter(tmp_path)  # nothing installed
        cap = adapter.capability(None)
        assert cap.supported is False

        skipped = AdapterResult.skipped(cap.id, cap.reason)
        assert skipped.failed is False
        assert skipped.attempted is False


class TestPathTraversal:
    def test_safe_target_rejects_escape(self, tmp_path):
        base = tmp_path / "Code" / "User"
        with pytest.raises(AdapterError, match="escapes"):
            vjson.safe_target(base.parent.parent / "elsewhere" / "x.json", base)

    def test_safe_target_accepts_nested_paths_inside(self, tmp_path):
        base = tmp_path / "Code" / "User"
        resolved = vjson.safe_target(base / "settings.json", base)
        assert resolved == (base / "settings.json").resolve()

    def test_safe_target_rejects_dotdot_segments(self, tmp_path):
        base = tmp_path / "Code" / "User"
        with pytest.raises(AdapterError, match="escapes"):
            vjson.safe_target("../evil/settings.json", base)


class TestJsoncScanner:
    def test_scan_finds_properties_in_order(self):
        text = '{"b": {"x": 1}, "a": [1, {"y": ","}], "s": "brace } in string"}'
        props = vjson.scan_top_level_properties(text)
        assert [p.name for p in props] == ["b", "a", "s"]
        by_name = {p.name: p for p in props}
        assert json.loads(vjson.strip_jsonc(text[by_name["a"].value_start:by_name["a"].value_end])) == [
            1, {"y": ","},
        ]

    def test_merge_property_reports_previous_value(self):
        text = '{"k": {"old": 1}}'
        new_text, previous = vjson.merge_property(text, "k", {"new": 2})
        assert previous == {"old": 1}
        assert json.loads(new_text) == {"k": {"new": 2}}

    def test_unterminated_string_raises(self):
        with pytest.raises(AdapterError, match="unterminated"):
            vjson.loads('{"a": "open')

    def test_non_object_root_raises(self):
        with pytest.raises(AdapterError, match="object"):
            vjson.loads("[1,2]")


class TestJournalPersistence:
    def test_journal_round_trip_and_corruption_recovery(self, tmp_path):
        jp = tmp_path / "adapters" / "vscode.json"
        j = Journal.load(jp)
        j.previous_values = {"focusBorder": None}
        j.generation = "gen-1"
        j.save()
        loaded = Journal.load(jp)
        assert loaded.generation == "gen-1"
        assert loaded.previous_values == {"focusBorder": None}

        jp.write_text("{not json")
        recovered = Journal.load(jp)
        assert recovered.previous_values == {}
