"""Shared fixtures for omni-theme-cachy unit tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.activation import ActivationContext  # noqa: E402
from core.state import RuntimeState  # noqa: E402
from core.staging import Manifest  # noqa: E402

# A complete, known-good palette mirroring themes/default. Inlined on
# purpose so these tests stay hermetic w.r.t. shipped assets.
_SEMANTIC = {
    "background": "#14161c",
    "darker_background": "#0e1015",
    "dark_background": "#101218",
    "lighter_background": "#1a1d25",
    "foreground": "#d6dae2",
    "bright_foreground": "#f5f7fa",
    "light_foreground": "#eef0f4",
    "dark_foreground": "#8a919d",
    "muted": "#7d8593",
    "accent": "#4f9eea",
    "accent_secondary": "#8f6caf",
    "selection": "#294664",
    "success": "#82a55b",
    "warning": "#d9a05b",
    "error": "#d9564f",
    "info": "#5b8ec4",
    "red": "#d9564f",
    "green": "#82a55b",
    "yellow": "#d9a05b",
    "blue": "#5b8ec4",
    "magenta": "#a064ca",
    "cyan": "#54a8ae",
    "bright_red": "#e8878f",
    "bright_green": "#9cc98f",
    "bright_yellow": "#e6be86",
    "bright_blue": "#82abdc",
    "bright_magenta": "#bb8ade",
    "bright_cyan": "#74c4ca",
}

_ANSI = [
    "#2a2e39", "#d9564f", "#82a55b", "#d9a05b",
    "#5b8ec4", "#a064ca", "#54a8ae", "#c5cbd6",
    "#565d6d", "#e8878f", "#9cc98f", "#e6be86",
    "#82abdc", "#bb8ade", "#74c4ca", "#eceff4",
]

FULL_PALETTE: dict[str, str] = {
    **_SEMANTIC,
    **{f"color{i}": c for i, c in enumerate(_ANSI)},
}

THEME_TOML = """\
[theme]
name = "Test"
id = "test"
version = 1
mode = "{mode}"

[wallpaper]
default = "wallpapers/test.png"
"""

# Mirrors the shipped themes/default/surfaces.toml so fixture themes are
# validation-clean by default.
SURFACES_TOML = """\
[popups]
background = "#1e222b"
border = "#4f9eea"
border-width = 2

[controls]
normal-border = "#3a4150"
focus-border = "rgba(4f9eeaee) rgba(8f6cafee) 45deg"
"""


def _toml_scalar(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def surfaces_toml_text(groups: dict[str, dict]) -> str:
    """Render ``{group: {key: value}}`` to TOML text (no writer in stdlib)."""
    chunks = []
    for group, entries in groups.items():
        lines = [f"[{group}]"]
        lines += [f"{k} = {_toml_scalar(v)}" for k, v in entries.items()]
        chunks.append("\n".join(lines))
    return "\n\n".join(chunks) + "\n"


def write_theme(
    directory: Path,
    *,
    mode: str = "dark",
    colors: dict[str, str] | None = None,
    omit: frozenset[str] | set[str] = frozenset(),
    theme_toml: str | None = None,
    surfaces: str | dict[str, dict] | None = SURFACES_TOML,
) -> Path:
    """Materialize a theme directory under *directory* and return its path.

    ``surfaces`` may be TOML text, a nested dict, or ``None`` to ship no
    surfaces at all.
    """
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "theme.toml").write_text(
        theme_toml if theme_toml is not None else THEME_TOML.format(mode=mode)
    )
    palette = {k: v for k, v in FULL_PALETTE.items() if k not in omit}
    palette.update(colors or {})
    lines = "\n".join(f'{role} = "{value}"' for role, value in palette.items())
    (directory / "colors.toml").write_text(lines + "\n")
    if surfaces is not None:
        text = surfaces_toml_text(surfaces) if isinstance(surfaces, dict) else surfaces
        (directory / "surfaces.toml").write_text(text)
    return directory


@pytest.fixture
def palette_dict() -> dict[str, str]:
    return dict(FULL_PALETTE)


@pytest.fixture
def make_theme(tmp_path):
    """Factory building complete (or deliberately broken) theme dirs."""
    counter = iter(range(10_000))

    def make(name: str | None = None, **kwargs) -> Path:
        label = name or f"theme-{next(counter)}"
        return write_theme(tmp_path / label, **kwargs)

    return make


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """Redirect HOME and all XDG roots into *tmp_path*.

    Engine path helpers read the environment at call time, so runtime
    directories created after this fixture never touch the real $HOME.
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    for var in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME"):
        monkeypatch.delenv(var, raising=False)
    return home


FIXED_TIMESTAMP = "2026-01-01T00:00:00+00:00"


@pytest.fixture
def state_root(tmp_path):
    """A self-consistent, populated runtime state directory.

    Mirrors what activation leaves behind: one active generation
    (``gen-1``), one rollback target (``gen-0``), matching ``current`` /
    ``previous`` symlinks and a recorded state.json — so ``status`` /
    ``doctor`` see a consistent, non-empty runtime.
    """
    from core.state import CURRENT_LINK, PREVIOUS_LINK, ensure_layout, switch_link, write_state
    from core.staging import manifest_to_dict
    from core.staging import Manifest

    root = ensure_layout(tmp_path / "state")

    def _write_generation(gen_id: str, theme_name: str, theme_id: str) -> None:
        gen_dir = root / "generations" / gen_id
        gen_dir.mkdir(parents=True, exist_ok=True)
        manifest = Manifest(
            theme_name=theme_name,
            theme_id=theme_id,
            theme_version=1,
            mode="dark",
            theme_source=Path("themes"),
            timestamp=FIXED_TIMESTAMP,
            ownership="base",
            files=(),
        )
        (gen_dir / "manifest.json").write_text(
            json.dumps(manifest_to_dict(manifest), indent=2) + "\n"
        )

    _write_generation("gen-1", "Test", "test")
    _write_generation("gen-0", "Old", "old")
    switch_link(root, CURRENT_LINK, "gen-1")
    switch_link(root, PREVIOUS_LINK, "gen-0")
    write_state(
        root,
        RuntimeState(
            current_theme="test",
            previous_theme="old",
            activated_at="2026-01-01T00:00:00+00:00",
            current_generation="gen-1",
            previous_generation="gen-0",
            managed_targets=(),
            adapters={"kde": {"supported": True, "applied": True, "verified": True}},
        ),
    )
    return root


@pytest.fixture
def context_factory(tmp_path, make_theme):
    """Build an ActivationContext against a sandbox state root.

    ``files`` accepts (name, source, target, adapter, staged) tuples that
    become manifest entries; matching staged placeholder files are created
    under the generation dir.
    """

    def factory(*, theme=None, files=(), state_root=None, timestamp=FIXED_TIMESTAMP):
        generation = tmp_path / "generation"
        generation.mkdir(parents=True, exist_ok=True)
        entries = []
        for name, source, target, adapter, staged in files:
            artifact = generation / staged
            artifact.parent.mkdir(parents=True, exist_ok=True)
            if not artifact.exists():
                artifact.write_text("placeholder\n")
            entries.append(
                _entry(name=name, source=source, target=target,
                       adapter=adapter, staged=staged)
            )
        manifest = Manifest(
            theme_name="Test",
            theme_id="test",
            theme_version=1,
            mode="dark",
            theme_source=Path("."),
            timestamp=timestamp,
            ownership="base",
            files=tuple(entries),
        )
        return ActivationContext(
            state_root=state_root or tmp_path / "state",
            generation_dir=generation,
            manifest=manifest,
            theme=theme,
            dry_run=False,
            previous_state=RuntimeState(),
        )

    return factory


def _entry(*, name, source, target, adapter, staged):
    from core.staging import ManifestFileEntry

    return ManifestFileEntry(
        name=name,
        source=source,
        origin="builtin",
        target=str(target),
        adapter=adapter,
        hash="0" * 64,
        staged=staged,
    )
