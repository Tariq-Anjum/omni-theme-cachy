"""Shared sandbox for the security test group (session 08).

Everything runs inside ``tmp_path``: the autouse ``_approved_roots_sandbox``
fixture in ``tests/conftest.py`` redirects HOME/XDG and points the central
write-policy allowlist at the sandbox, so no test ever touches the real
home directory or real desktop configuration.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import write_theme

#: Two-template registry writing one file per XDG base directory.
REGISTRY = """
[[template]]
adapter = "test"

[template.source]
path = "app/one.conf.tpl"

[template.target]
path = "~/.local/share/omni-test/one.conf"

[[template]]
[template.source]
path = "app/two.conf.tpl"

[template.target]
path = "~/.config/omni-test/two.conf"
"""


@pytest.fixture
def sandbox(tmp_path):
    """Templates, registry and a valid theme, all inside the sandbox."""
    app = tmp_path / "templates" / "app"
    app.mkdir(parents=True)
    (app / "one.conf.tpl").write_text("one={{ accent }}\n")
    (app / "two.conf.tpl").write_text("two={{ foreground }}\n")
    registry = tmp_path / "templates" / "targets.toml"
    registry.write_text(REGISTRY)
    # No [wallpaper] section: no wallpaper assets are shipped in the sandbox.
    theme = write_theme(
        tmp_path / "themes" / "alpha",
        theme_toml='[theme]\nname = "Alpha"\nid = "alpha"\nversion = 1\nmode = "dark"\n',
    )
    return {
        "registry": registry,
        "templates_root": tmp_path / "templates",
        "theme": theme,
        "targets": (
            tmp_path / "home" / ".local" / "share" / "omni-test" / "one.conf",
            tmp_path / "home" / ".config" / "omni-test" / "two.conf",
        ),
    }


@pytest.fixture
def allow(tmp_path):
    """Narrow the policy to a single approved root: ``tmp_path/allowed``.

    Everything else under *tmp_path* (including the sandbox home) is then
    *outside* the approved roots, so escape tests have somewhere real to
    escape to.
    """
    from core import filesystem

    root = tmp_path / "allowed"
    root.mkdir()
    filesystem.set_approved_roots([root])
    yield root
    filesystem.set_approved_roots(None)


@pytest.fixture
def fake_adapter_factory():
    """Factory for contract-conforming adapter stubs with failure modes."""

    def factory(
        adapter_id: str,
        *,
        supported: bool = True,
        critical: bool = False,
        fail_apply: bool = False,
        fail_verify: bool = False,
        fail_rollback: bool = False,
    ):
        from core.adapters import AdapterCapability, AdapterResult

        class StubAdapter:
            id = adapter_id

            def capability(self, context):
                return AdapterCapability(
                    id=adapter_id, supported=supported, version="1"
                )

            def plan(self, resolved_theme, context):
                return {"theme": resolved_theme.meta.id}

            def render(self, resolved_theme, staging, context):
                return None

            def apply(self, plan, context):
                if fail_apply:
                    raise RuntimeError(f"{adapter_id} apply exploded")
                return AdapterResult(adapter_id=adapter_id, applied=True)

            def verify(self, plan, context):
                if fail_verify:
                    return AdapterResult(
                        adapter_id=adapter_id, applied=True, verified=False,
                        errors=(f"{adapter_id} verify failed",),
                    )
                return AdapterResult(adapter_id=adapter_id, applied=True, verified=True)

            def rollback(self, previous_state, context):
                if fail_rollback:
                    raise RuntimeError(f"{adapter_id} rollback exploded")
                return AdapterResult(adapter_id=adapter_id, rolled_back=True)

        stub = StubAdapter()
        return stub, critical

    return factory
