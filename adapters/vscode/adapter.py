"""VS Code adapter: merge Omni colors into ``<User>/settings.json``.

Ownership boundary
------------------
Omni owns exactly one property inside settings.json:
``workbench.colorCustomizations`` — and within it, only the keys listed
in :data:`adapters.vscode.mapping.MANAGED_KEYS`. Everything else in the
file is user state and is preserved **byte-for-byte** (comments
included) via JSONC surgery (:mod:`adapters.vscode.jsonc`).

Metadata lives in Omni's own journal
(``<state>/adapters/vscode.json``), *not* in a ``_omniTheme`` key:
settings.json is schema-checked by VS Code, and injecting unknown root
keys risks editor warnings for zero benefit. The journal records which
managed keys were written, what their previous values were (for exact
rollback), whether colorCustomizations existed before us, and the file
hash before our write (user-modification detection).

Merge policy
------------
* managed keys absent before → added;
* managed keys present with values we wrote → updated;
* managed keys the user changed since our last write → overwritten,
  with an explicit warning naming each clobbered user value;
* unknown keys inside colorCustomizations → never touched.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from core.adapters import AdapterCapability, AdapterResult
from core.errors import AdapterError
from core.filesystem import atomic_write_text, sha256_file

from adapters.vscode import jsonc as vscode_jsonc
from adapters.vscode.mapping import (
    COLOR_CUSTOMIZATIONS_KEY,
    MANAGED_KEYS,
    vscode_color_customizations,
)

__all__ = ["VscodeAdapter", "VscodePlan", "Journal", "journal_path", "discover_settings_file"]

#: Candidate app directories under ``$XDG_CONFIG_HOME``, in probe order.
APP_DIRS: tuple[str, ...] = ("Code", "Code - OSS", "VSCodium")

JOURNAL_FILE = "vscode.json"


def discover_settings_file(config_home: Path | None = None) -> Path | None:
    """First existing ``<app>/User`` directory → its settings.json path.

    Returns None when no VS Code family installation is found. A missing
    settings.json inside an existing User dir still yields a path: an
    empty configuration is supported.
    """
    base = Path(config_home) if config_home else _config_home()
    for app in APP_DIRS:
        user_dir = base / app / "User"
        if user_dir.is_dir():
            return user_dir / "settings.json"
    return None


def _config_home() -> Path:
    from core.filesystem import xdg_config_home  # call-time resolution

    return xdg_config_home()


def journal_path(state_root: str | Path) -> Path:
    """Adapter-private record under the engine state root."""
    return Path(state_root) / "adapters" / JOURNAL_FILE


@dataclass
class Journal:
    """Previous-values record enabling exact rollback of managed keys."""

    path: Path
    generation: str | None = None
    theme_id: str | None = None
    #: managed key → previous value; missing keys are recorded as null.
    previous_values: dict[str, object] = field(default_factory=dict)
    customizations_existed: bool = False
    file_hash_before: str | None = None

    @classmethod
    def load(cls, path: str | Path) -> "Journal":
        p = Path(path)
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return cls(path=p)
        except (OSError, json.JSONDecodeError):
            return cls(path=p)  # corrupt record: start fresh, never brick
        if not isinstance(raw, dict):
            return cls(path=p)
        values = raw.get("previous_values")
        return cls(
            path=p,
            generation=raw.get("generation") if isinstance(raw.get("generation"), str) else None,
            theme_id=raw.get("theme_id") if isinstance(raw.get("theme_id"), str) else None,
            previous_values=dict(values) if isinstance(values, dict) else {},
            customizations_existed=bool(raw.get("customizations_existed")),
            file_hash_before=(
                raw.get("file_hash_before")
                if isinstance(raw.get("file_hash_before"), str)
                else None
            ),
        )

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {
                    "generation": self.generation,
                    "theme_id": self.theme_id,
                    "previous_values": self.previous_values,
                    "customizations_existed": self.customizations_existed,
                    "file_hash_before": self.file_hash_before,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


@dataclass(frozen=True)
class VscodePlan:
    """Read-only intent for one activation."""

    settings_path: Path
    #: The colorCustomizations this activation intends to write.
    customizations: dict[str, str]
    generation: str
    theme_id: str
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "settings_path": str(self.settings_path),
            "customizations": dict(self.customizations),
            "generation": self.generation,
            "theme_id": self.theme_id,
            "warnings": list(self.warnings),
        }


class VscodeAdapter:
    """Applies Omni colors to VS Code via workbench.colorCustomizations.

    All I/O goes through injectable seams (*which*, *config home*) so
    tests run hermetically without VS Code installed.
    """

    id = "vscode"

    def __init__(
        self,
        *,
        config_home: Path | None = None,
    ) -> None:
        self._config_home = config_home

    # -- discovery -----------------------------------------------------------

    def settings_file(self) -> Path | None:
        return discover_settings_file(
            self._config_home if self._config_home else None
        )

    # -- contract phases -------------------------------------------------------

    def capability(self, context) -> AdapterCapability:
        settings = self.settings_file()
        if settings is None:
            installed = [app for app in APP_DIRS if (self._base() / app).is_dir()]
            reason = (
                "VS Code family not installed "
                f"(no {', '.join(APP_DIRS)} under config home)"
                if not installed
                else f"VS Code found ({installed[0]}) but has no User directory"
            )
            return AdapterCapability(id=self.id, supported=False, reason=reason)
        return AdapterCapability(id=self.id, supported=True)

    def _base(self) -> Path:
        return self._config_home if self._config_home else _config_home()

    def plan(self, resolved_theme, context) -> VscodePlan:
        settings = self.settings_file()
        if settings is None:  # capability() guards this; defensive anyway
            raise AdapterError("cannot plan vscode adapter: settings.json not discovered")

        warnings: list[str] = []
        if settings.is_file():
            try:
                vscode_jsonc.loads(settings.read_text(encoding="utf-8"))
            except (AdapterError, OSError) as exc:
                warnings.append(
                    f"existing settings.json unreadable ({exc}); apply will refuse to touch it"
                )

        generation = ""
        manifest = getattr(context, "manifest", None)
        if manifest is not None:
            generation = str(getattr(manifest, "timestamp", "") or "")

        return VscodePlan(
            settings_path=vscode_jsonc.safe_target(settings, self._base()),
            customizations=vscode_color_customizations(resolved_theme),
            generation=generation,
            theme_id=resolved_theme.meta.id,
            warnings=tuple(warnings),
        )

    def render(self, resolved_theme, staging, context) -> None:
        """Nothing staged for this adapter: output is computed at apply time."""

    def apply(self, plan: VscodePlan, context) -> AdapterResult:
        errors: list[str] = []
        warnings: list[str] = list(plan.warnings)

        settings = plan.settings_path
        raw = ""
        if settings.is_file():
            try:
                raw = settings.read_text(encoding="utf-8")
            except OSError as exc:
                errors.append(f"cannot read {settings}: {exc}")
                return self._result(applied=False, warnings=warnings, errors=errors)

        # Merge into any existing colorCustomizations: unknown user keys
        # inside it are preserved, managed keys are updated.
        existing: dict | None = None
        try:
            if raw.strip():
                parsed_root = vscode_jsonc.loads(raw)  # AdapterError → refuse
                candidate = parsed_root.get(COLOR_CUSTOMIZATIONS_KEY)
                existing = candidate if isinstance(candidate, dict) else None
            merged = dict(existing or {})
            merged.update(plan.customizations)
            new_text, previous = vscode_jsonc.merge_property(
                raw, COLOR_CUSTOMIZATIONS_KEY, merged
            )
        except AdapterError as exc:
            errors.append(str(exc))
            return self._result(applied=False, warnings=warnings, errors=errors)

        journal = Journal.load(journal_path(context.state_root))
        journal.previous_values = {
            key: previous.get(key) if isinstance(previous, dict) else None
            for key in sorted(MANAGED_KEYS & set(plan.customizations))
        }
        journal.customizations_existed = isinstance(previous, dict)
        journal.file_hash_before = (
            sha256_file(settings) if settings.is_file() else None
        )
        journal.generation = plan.generation
        journal.theme_id = plan.theme_id

        # Any managed key holding a value other than ours is replaced;
        # say so explicitly instead of silently clobbering user work.
        if isinstance(previous, dict):
            for key in sorted(MANAGED_KEYS & set(previous)):
                old_value = previous[key]
                if key in plan.customizations and old_value != plan.customizations[key]:
                    warnings.append(
                        f"replacing {COLOR_CUSTOMIZATIONS_KEY}.{key} "
                        f"(was {json.dumps(old_value)})"
                    )

        try:
            if new_text != raw or not settings.is_file():
                atomic_write_text(settings, new_text)
        except OSError as exc:
            errors.append(f"cannot write {settings}: {exc}")
            return self._result(applied=False, warnings=warnings, errors=errors)

        journal.save()
        return self._result(applied=True, warnings=warnings, errors=errors)

    def verify(self, plan: VscodePlan, context) -> AdapterResult:
        errors: list[str] = []
        settings = plan.settings_path
        try:
            current = vscode_jsonc.loads(settings.read_text(encoding="utf-8"))
        except (OSError, AdapterError) as exc:
            errors.append(f"cannot verify {settings}: {exc}")
            return self._result(applied=True, verified=False, errors=errors)

        actual = current.get(COLOR_CUSTOMIZATIONS_KEY)
        if not isinstance(actual, dict):
            errors.append(f"{COLOR_CUSTOMIZATIONS_KEY} missing from settings.json")
            return self._result(applied=True, verified=False, errors=errors)

        for key, expected in plan.customizations.items():
            got = actual.get(key)
            if got != expected:
                errors.append(
                    f"{COLOR_CUSTOMIZATIONS_KEY}.{key} is {got!r}, expected {expected!r}"
                )
        return self._result(applied=True, verified=not errors, errors=errors)

    def rollback(self, previous_state, context) -> AdapterResult:
        errors: list[str] = []
        warnings: list[str] = []
        journal = Journal.load(journal_path(context.state_root))

        settings = self.settings_file()
        if settings is None:
            warnings.append("no VS Code installation; nothing to roll back")
            return AdapterResult(adapter_id=self.id, rolled_back=True, warnings=tuple(warnings))
        if not journal.previous_values and journal.file_hash_before is None:
            warnings.append("no vscode journal record; nothing to revert")
            return AdapterResult(adapter_id=self.id, rolled_back=True, warnings=tuple(warnings))

        try:
            raw = settings.read_text(encoding="utf-8") if settings.is_file() else ""
            if not settings.is_file():
                warnings.append("settings.json vanished; nothing to revert")
                return AdapterResult(adapter_id=self.id, rolled_back=True, warnings=tuple(warnings))
            if journal.customizations_existed:
                new_text, removed = vscode_jsonc.remove_keys_from_property(
                    raw, COLOR_CUSTOMIZATIONS_KEY, tuple(MANAGED_KEYS)
                )
                if removed:
                    restored = {
                        k: v for k, v in journal.previous_values.items() if v is not None
                    }
                    if restored:
                        new_text, _ = vscode_jsonc.merge_property(
                            new_text, COLOR_CUSTOMIZATIONS_KEY, restored
                        )
            else:
                # We introduced the property; remove it wholesale.
                new_text = vscode_jsonc.remove_property(raw, COLOR_CUSTOMIZATIONS_KEY)
            atomic_write_text(settings, new_text)
        except (OSError, AdapterError) as exc:
            errors.append(f"vscode rollback failed: {exc}")

        return AdapterResult(
            adapter_id=self.id,
            rolled_back=not errors,
            warnings=tuple(warnings),
            errors=tuple(errors),
        )

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _result(*, applied=False, verified=False, rolled_back=False,
                warnings=(), errors=()) -> AdapterResult:
        return AdapterResult(
            adapter_id="vscode",
            attempted=True,
            applied=applied,
            verified=verified,
            rolled_back=rolled_back,
            supported=True,
            warnings=tuple(warnings),
            errors=tuple(errors),
        )
