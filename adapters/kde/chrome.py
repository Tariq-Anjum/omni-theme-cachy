"""Plasma chrome adapter: panels, window decorations and tooltips.

Where the KDE adapter themes application colors through the Color
Scheme system, this adapter covers the *shell chrome* the scheme does
not reach. It writes **no whole files**: every target is KDE user state
(``plasma-org.kde.plasma.desktop-appletsrc``, ``kwinrc``,
``kdeglobals``), so it performs surgical, byte-preserving key edits via
:mod:`core.kde_config` — the same ownership model as the Konsole
adapter — and journals the previous value of every key it touches for
exact rollback.

Theme vocabulary (``surfaces.toml`` groups; absent groups are skipped):

.. code-block:: toml

    [panel]
    opacity = "translucent"   # opaque | translucent | adaptive

    [kwin]
    theme = "Purple"          # kwinrc [org.kde.kdecoration2] theme
    library = "org.kde.kwin.aurorae"   # optional, only when authored

    [tooltips]
    background = "#rrggbb"    # kdeglobals [Colors:Tooltip] Background*
    foreground = "#rrggbb"    # kdeglobals [Colors:Tooltip] Foreground*

Panel opacity maps to ``[PlasmaViews][Panel <id>][Defaults] opacity``
(0 = opaque, 1 = translucent, 2 = adaptive) for every containment whose
``plugin`` is ``org.kde.panel``. After writing, plasmashell and KWin
are asked to reconfigure (best effort) so changes apply live.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from core.adapters import AdapterCapability, AdapterResult
from core.errors import AdapterError
from core.filesystem import atomic_write_text
from core import kde_config

from adapters import support as adapter_support
from adapters.kde.detection import PlasmaEnvironment, detect_plasma

__all__ = ["PlasmaChromeAdapter", "ChromePlan", "Journal", "journal_path"]

JOURNAL_FILE = "chrome.json"

APPLETSRC = "plasma-org.kde.plasma.desktop-appletsrc"
KWINRC = "kwinrc"
KDEGLOBALS = "kdeglobals"

PANEL_PLUGIN = "org.kde.panel"
OPACITY_CODES = {"opaque": 0, "translucent": 1, "adaptive": 2}

_TOOLTIP_KEYS = {
    "background": ("BackgroundNormal", "BackgroundAlternate"),
    "foreground": ("ForegroundNormal", "ForegroundInactive"),
}


def journal_path(state_root: str | Path) -> Path:
    return Path(state_root) / "adapters" / JOURNAL_FILE


@dataclass
class Journal:
    """Pre-apply state enabling exact rollback of everything we touch."""

    path: Path
    #: ``{file: snapshot_record}`` — first-apply bytes of each touched file.
    snapshots: dict = None  # type: ignore[assignment]
    #: ``[{file, section, key, previous, existed}, …]``
    patches: list = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.snapshots is None:
            self.snapshots = {}
        if self.patches is None:
            self.patches = []

    @classmethod
    def load(cls, path: str | Path) -> "Journal":
        p = Path(path)
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls(path=p)
        if not isinstance(raw, dict):
            return cls(path=p)
        return cls(
            path=p,
            snapshots=raw.get("snapshots", {}) if isinstance(raw.get("snapshots"), dict) else {},
            patches=raw.get("patches", []) if isinstance(raw.get("patches"), list) else [],
        )

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            self.path,
            json.dumps({"snapshots": self.snapshots, "patches": self.patches}, indent=2) + "\n",
        )


@dataclass(frozen=True)
class ChromePatch:
    """One surgical key edit planned for a config file."""

    #: File name inside ``~/.config``.
    file: str
    #: Nested KConfig group path, e.g. ``PlasmaViews][Panel 3][Defaults``.
    section: str
    key: str
    value: str
    label: str

    def to_dict(self) -> dict:
        return {
            "file": self.file, "section": self.section,
            "key": self.key, "value": self.value, "label": self.label,
        }


@dataclass(frozen=True)
class ChromePlan:
    """Read-only intent for one activation."""

    patches: tuple[ChromePatch, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "patches": [p.to_dict() for p in self.patches],
            "warnings": list(self.warnings),
        }


class PlasmaChromeAdapter:
    """Applies panel/decoration/tooltip chrome from theme surfaces."""

    id = "plasma-chrome"

    def __init__(
        self,
        *,
        env: dict | None = None,
        which=None,
        config_home: str | Path | None = None,
    ) -> None:
        kwargs: dict = {}
        if env is not None:
            kwargs["env"] = env
        if which is not None:
            kwargs["which"] = which
        self._kwargs = kwargs
        self._config_home = Path(config_home).expanduser() if config_home else None
        self._detected: PlasmaEnvironment | None = None

    def environment(self) -> PlasmaEnvironment:
        if self._detected is None:
            self._detected = detect_plasma(**self._kwargs)
        return self._detected

    def _config_file(self, name: str) -> Path:
        if self._config_home is not None:
            return self._config_home / name
        from core.filesystem import xdg_config_home

        return xdg_config_home() / name

    def _reconfigure(self) -> None:
        """Ask plasmashell/KWin to reload their configs (best effort)."""
        bus = shutil.which("qdbus6") or shutil.which("qdbus")
        if not bus:
            return
        import subprocess

        for service, path, interface in (
            ("org.kde.plasmashell", "/PlasmaShell", "org.kde.PlasmaShell.reconfigure"),
            ("org.kde.KWin", "/KWin", "org.kde.KWin.reconfigure"),
        ):
            try:
                subprocess.run(
                    [bus, service, path, interface],
                    capture_output=True, timeout=5,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue

    # -- surfaces → patches ----------------------------------------------------

    def build_patches(self, resolved_theme) -> tuple[ChromePatch, ...]:
        """Compute the patch list from theme surfaces (pure, no I/O)."""
        patches: list[ChromePatch] = []
        if resolved_theme is None or not resolved_theme.surfaces:
            return tuple(patches)

        surfaces = resolved_theme.surfaces

        # 1. Panel opacity → appletsrc (every panel containment).
        opacity = surfaces.get("panel", "opacity")
        if opacity is not None:
            if isinstance(opacity, int) and opacity in (0, 1, 2):
                code = opacity
            else:
                code = OPACITY_CODES.get(str(opacity).strip().lower())
            if code is None:
                raise AdapterError(
                    f"[panel] opacity must be one of "
                    f"{', '.join(OPACITY_CODES)} (or 0/1/2), got {opacity!r}"
                )
            for containment_id in self._panel_containment_ids():
                patches.append(
                    ChromePatch(
                        file=APPLETSRC,
                        section=f"PlasmaViews][Panel {containment_id}][Defaults",
                        key="opacity",
                        value=str(code),
                        label=f"panel[{containment_id}] opacity={opacity}",
                    )
                )

        # 2. Window decoration → kwinrc.
        kwin_theme = surfaces.get("kwin", "theme")
        if kwin_theme is not None:
            patches.append(
                ChromePatch(file=KWINRC, section="org.kde.kdecoration2",
                            key="theme", value=str(kwin_theme),
                            label=f"kwin decoration theme={kwin_theme}")
            )
        kwin_library = surfaces.get("kwin", "library")
        if kwin_library is not None:
            patches.append(
                ChromePatch(file=KWINRC, section="org.kde.kdecoration2",
                            key="library", value=str(kwin_library),
                            label=f"kwin decoration library={kwin_library}")
            )

        # 3. Tooltip colors → kdeglobals [Colors:Tooltip].
        tooltips = surfaces.group("tooltips") if surfaces else {}
        for role, value in tooltips.items():
            if role not in _TOOLTIP_KEYS:
                continue
            hex_value = _as_kconfig_rgb(value)
            for key in _TOOLTIP_KEYS[role]:
                patches.append(
                    ChromePatch(file=KDEGLOBALS, section="Colors:Tooltip",
                                key=key, value=hex_value,
                                label=f"tooltip {key}={hex_value}")
                )
        return tuple(patches)

    def _panel_containment_ids(self) -> list[str]:
        """Containment ids whose ``plugin`` is ``org.kde.panel``."""
        appletsrc = self._config_file(APPLETSRC)
        try:
            text = appletsrc.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        except OSError as exc:
            raise AdapterError(f"cannot read {appletsrc}: {exc}") from exc
        ids: list[str] = []
        for (section, key), value in kde_config.parse_ini(text).items():
            if key != "plugin" or value.strip() != PANEL_PLUGIN:
                continue
            if not section.startswith("Containments]["):
                continue
            containment_id = section.rsplit("][", 1)[-1]
            if containment_id and containment_id not in ids:
                ids.append(containment_id)
        return ids

    # -- contract phases -------------------------------------------------------

    def capability(self, context) -> AdapterCapability:
        env = self.environment()
        if not env.is_plasma_session and env.plasmashell_version is None:
            return AdapterCapability(
                id=self.id,
                supported=False,
                reason="no KDE Plasma session detected "
                f"(XDG_CURRENT_DESKTOP={env.desktop!r})",
            )
        return AdapterCapability(id=self.id, supported=True)

    def plan(self, resolved_theme, context) -> ChromePlan:
        warnings: list[str] = []
        patches = self.build_patches(resolved_theme)
        if not patches:
            warnings.append(
                "no [panel]/[kwin]/[tooltips] surfaces declared; "
                "plasma-chrome has nothing to apply"
            )
        return ChromePlan(patches=patches, warnings=tuple(warnings))

    def render(self, resolved_theme, staging, context) -> None:
        """No staged artifacts: chrome edits are applied in-place."""

    def apply(self, plan: ChromePlan, context) -> AdapterResult:
        warnings: list[str] = list(plan.warnings)
        if not plan.patches:
            return AdapterResult(
                adapter_id=self.id, attempted=True, applied=True,
                supported=True, warnings=tuple(warnings),
            )

        journal = Journal.load(journal_path(context.state_root))
        backup_root = Path(context.state_root) / "adapters" / "chrome-backups"
        previous: list[dict] = list(journal.patches)
        errors: list[str] = []

        by_file: dict[str, list[ChromePatch]] = {}
        for patch in plan.patches:
            by_file.setdefault(patch.file, []).append(patch)

        for file_name, file_patches in by_file.items():
            target = self._config_file(file_name)
            try:
                text = target.read_text(encoding="utf-8") if target.is_file() else ""
                if file_name not in journal.snapshots:
                    journal.snapshots[file_name] = (
                        adapter_support.snapshot_file(target, backup_root)
                        if target.is_file() else {"existed_before": False}
                    )
                new_text = text
                for patch in file_patches:
                    new_text, prev_value, existed = kde_config.set_ini_key(
                        new_text, patch.section, patch.key, patch.value
                    )
                    previous.append({
                        "file": file_name, "section": patch.section,
                        "key": patch.key, "previous": prev_value,
                        "existed": existed,
                    })
                atomic_write_text(target, new_text)
            except (OSError, AdapterError) as exc:
                errors.append(f"{file_name}: {exc}")

        if errors:
            return AdapterResult(
                adapter_id=self.id, attempted=True, applied=False,
                supported=True, warnings=tuple(warnings), errors=tuple(errors),
            )

        journal.patches = previous
        journal.save()
        self._reconfigure()
        return AdapterResult(
            adapter_id=self.id, attempted=True, applied=True,
            supported=True, warnings=tuple(warnings),
        )

    def verify(self, plan: ChromePlan, context) -> AdapterResult:
        if not plan.patches:
            return AdapterResult(
                adapter_id=self.id, attempted=True, applied=True,
                verified=True, supported=True,
            )
        errors: list[str] = []
        by_file: dict[str, list[ChromePatch]] = {}
        for patch in plan.patches:
            by_file.setdefault(patch.file, []).append(patch)

        for file_name, file_patches in by_file.items():
            target = self._config_file(file_name)
            try:
                text = target.read_text(encoding="utf-8")
            except OSError as exc:
                errors.append(f"cannot verify {target}: {exc}")
                continue
            entries = kde_config.parse_ini(text)
            for patch in file_patches:
                actual = entries.get((patch.section, patch.key))
                if actual is None or actual.strip() != patch.value:
                    errors.append(
                        f"{file_name} [{patch.section}] {patch.key} is "
                        f"{actual!r}, expected {patch.value!r}"
                    )
        return AdapterResult(
            adapter_id=self.id, attempted=True, applied=True,
            verified=not errors, supported=True, errors=tuple(errors),
        )

    def rollback(self, previous_state, context) -> AdapterResult:
        journal = Journal.load(journal_path(context.state_root))
        if not journal.snapshots:
            return AdapterResult(
                adapter_id=self.id,
                rolled_back=True,
                warnings=("no chrome journal record; nothing to revert",),
            )
        errors: list[str] = []
        warnings: list[str] = []
        backup_root = Path(context.state_root) / "adapters" / "chrome-backups"
        for file_name, record in journal.snapshots.items():
            target = self._config_file(file_name)
            if record.get("existed_before") is False:
                try:
                    target.unlink(missing_ok=True)
                except OSError as exc:
                    errors.append(f"cannot remove {target}: {exc}")
                continue
            rolled, warns = adapter_support.restore_snapshot(target, record)
            warnings.extend(warns)
            if not rolled:
                errors.extend(warns)
        if not errors:
            journal.snapshots = {}
            journal.patches = []
            journal.save()
            self._reconfigure()
        return AdapterResult(
            adapter_id=self.id, rolled_back=not errors,
            warnings=tuple(warnings), errors=tuple(errors),
        )


def _as_kconfig_rgb(value: object) -> str:
    """``#rrggbb`` → ``r,g,b`` KConfig triplet (AdapterError otherwise)."""
    from core.color import strip_hex
    from core.errors import ColorError

    try:
        hex_digits = strip_hex(str(value))
    except ColorError as exc:
        raise AdapterError(f"[tooltips] {exc}") from exc
    if len(hex_digits) == 3:
        hex_digits = "".join(ch * 2 for ch in hex_digits)
    try:
        r, g, b = (int(hex_digits[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError as exc:
        raise AdapterError(f"[tooltips] malformed color {value!r}") from exc
    return f"{r},{g},{b}"
