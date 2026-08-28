"""Konsole terminal adapter (the one explicitly supported terminal).

Konsole is chosen because it is the KDE-native terminal: it shares the
Color Scheme ecosystem this project already drives, and its profile →
colorscheme model is documented and stable.

Ownership boundary
------------------
* **Owned** (generated artifact, safe to overwrite):
  ``~/.local/share/konsole/OmniTheme.colorscheme``.
* **User state** (modified surgically, journalled for exact rollback):
  the default profile file's ``[Appearance] ColorScheme=`` key. Every
  other byte and key of the profile is preserved verbatim; the previous
  value (or "key absent") plus a snapshot of prior bytes are recorded
  in ``<state>/adapters/konsole.json`` before touching anything.

If no default profile is configured in ``konsolerc``, the adapter
reports *unsupported* with that reason rather than guessing which
profile to edit — unsupported must not masquerade as failure.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from core.adapters import AdapterCapability, AdapterResult
from core.errors import AdapterError
from core.filesystem import atomic_write_text

from adapters import support as adapter_support
from adapters.konsole import colorscheme as kc
from adapters.konsole.detection import KonsoleEnvironment, detect_konsole

__all__ = ["KonsoleAdapter", "KonsolePlan", "Journal", "journal_path"]

JOURNAL_FILE = "konsole.json"

_APPEARANCE_GROUP = re.compile(r"^(\[Appearance\][^\n]*\n)", re.MULTILINE)


def journal_path(state_root: str | Path) -> Path:
    return Path(state_root) / "adapters" / JOURNAL_FILE


@dataclass
class Journal:
    """Pre-apply state enabling exact rollback of everything we touch."""

    path: Path
    scheme_existed: bool = False
    scheme_snapshot: dict | None = None
    profile_path: str | None = None
    profile_color_scheme_prev: str | None = None
    profile_key_existed: bool = False
    profile_snapshot: dict | None = None

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
            scheme_existed=bool(raw.get("scheme_existed")),
            scheme_snapshot=(
                raw["scheme_snapshot"] if isinstance(raw.get("scheme_snapshot"), dict) else None
            ),
            profile_path=raw.get("profile_path") if isinstance(raw.get("profile_path"), str) else None,
            profile_color_scheme_prev=(
                raw["profile_color_scheme_prev"]
                if isinstance(raw.get("profile_color_scheme_prev"), str)
                else None
            ),
            profile_key_existed=bool(raw.get("profile_key_existed")),
            profile_snapshot=(
                raw["profile_snapshot"]
                if isinstance(raw.get("profile_snapshot"), dict)
                else None
            ),
        )

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "scheme_existed": self.scheme_existed,
            "scheme_snapshot": self.scheme_snapshot,
            "profile_path": self.profile_path,
            "profile_color_scheme_prev": self.profile_color_scheme_prev,
            "profile_key_existed": self.profile_key_existed,
            "profile_snapshot": self.profile_snapshot,
        }
        atomic_write_text(self.path, json.dumps(payload, indent=2) + "\n")


@dataclass(frozen=True)
class KonsolePlan:
    """Read-only intent for one activation."""

    scheme_path: Path
    profile_path: Path
    rendered_scheme: str = ""
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "scheme_path": str(self.scheme_path),
            "profile_path": str(self.profile_path),
            "warnings": list(self.warnings),
        }


class KonsoleAdapter:
    """Applies Omni ANSI colors to Konsole via its colorscheme model."""

    id = "konsole"

    def __init__(
        self,
        *,
        env=None,
        which=None,
        config_home=None,
        data_home=None,
    ) -> None:
        kwargs: dict = {}
        if env is not None:
            kwargs["env"] = env
        if which is not None:
            kwargs["which"] = which
        if config_home is not None:
            kwargs["config_home"] = config_home
        if data_home is not None:
            kwargs["data_home"] = data_home
        self._kwargs = kwargs
        self._detected: KonsoleEnvironment | None = None

    def environment(self) -> KonsoleEnvironment:
        if self._detected is None:
            self._detected = detect_konsole(**self._kwargs)
        return self._detected

    # -- contract phases -------------------------------------------------------

    def capability(self, context) -> AdapterCapability:
        detected = self.environment()
        if not detected.installed:
            return AdapterCapability(
                id=self.id,
                supported=False,
                reason="konsole is not installed",
            )
        if detected.default_profile is None:
            return AdapterCapability(
                id=self.id,
                supported=False,
                reason="no [Desktop Entry] DefaultProfile in konsolerc; "
                "refusing to guess which profile to theme",
            )
        if detected.profile_path() is None:
            return AdapterCapability(
                id=self.id,
                supported=False,
                reason=f"default profile {detected.default_profile!r} "
                f"not found in {detected.profiles_dir}",
            )
        return AdapterCapability(id=self.id, supported=True)

    def plan(self, resolved_theme, context) -> KonsolePlan:
        detected = self.environment()
        palette = dict(resolved_theme.palette.colors)
        warnings: list[str] = []

        profiles_dir = detected.profiles_dir
        scheme_path = profiles_dir / kc.SCHEME_FILENAME
        profile = detected.profile_path()
        if profile is None or profiles_dir is None:
            # capability() guards this; keep plan total anyway.
            raise AdapterError("cannot plan konsole adapter: no default profile")

        return KonsolePlan(
            scheme_path=adapter_support.assert_within(profiles_dir, scheme_path),
            profile_path=adapter_support.assert_within(profiles_dir, profile),
            rendered_scheme=kc.render_colorscheme(palette),
            warnings=tuple(warnings),
        )

    def render(self, resolved_theme, staging, context) -> None:
        """No staged artifacts: the colorscheme text is computed in plan()."""

    def apply(self, plan: KonsolePlan, context) -> AdapterResult:
        errors: list[str] = []
        warnings: list[str] = list(plan.warnings)

        journal = Journal.load(journal_path(context.state_root))
        backup_root = Path(context.state_root) / "adapters" / "konsole-backups"
        try:
            # 1. owned artifact: write the generated colorscheme.
            # The pre-Omni snapshot is taken exactly once — on later runs
            # the file's current content *is* Omni's own output, which
            # must never replace the true original in the journal.
            if journal.scheme_snapshot is None:
                journal.scheme_existed = plan.scheme_path.is_file()
                journal.scheme_snapshot = (
                    adapter_support.snapshot_file(plan.scheme_path, backup_root)
                    if journal.scheme_existed
                    else {"existed_before": False}
                )
            atomic_write_text(plan.scheme_path, plan.rendered_scheme)

            # 2. user state: wire the profile's ColorScheme key surgically
            current_profile = plan.profile_path.read_text(encoding="utf-8")
            new_text, prev_value, key_existed = _set_profile_key(
                current_profile, kc.SCHEME_ID
            )
            if journal.profile_path != str(plan.profile_path):
                journal.profile_path = str(plan.profile_path)
                journal.profile_snapshot = adapter_support.snapshot_file(
                    plan.profile_path, backup_root
                )
                journal.profile_color_scheme_prev = prev_value
                journal.profile_key_existed = key_existed
            atomic_write_text(plan.profile_path, new_text)
        except (AdapterError, OSError) as exc:
            errors.append(f"konsole apply failed: {exc}")
            return AdapterResult(
                adapter_id=self.id, attempted=True, applied=False,
                supported=True, warnings=tuple(warnings), errors=tuple(errors),
            )

        journal.save()
        return AdapterResult(
            adapter_id=self.id,
            attempted=True,
            applied=True,
            supported=True,
            warnings=tuple(warnings),
        )

    def verify(self, plan: KonsolePlan, context) -> AdapterResult:
        errors: list[str] = []
        try:
            installed = plan.scheme_path.read_text(encoding="utf-8")
            profile_text = plan.profile_path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"cannot verify konsole files: {exc}")
            return AdapterResult(
                adapter_id=self.id, attempted=True, applied=True,
                verified=False, supported=True, errors=tuple(errors),
            )

        if installed != plan.rendered_scheme:
            errors.append(
                f"{plan.scheme_path} does not match the rendered scheme "
                "(modified after write?)"
            )
        entries = parse_profile_entries(profile_text)
        active = entries.get(("Appearance", "ColorScheme"))
        if active != kc.SCHEME_ID:
            errors.append(
                f"profile {plan.profile_path} selects ColorScheme={active!r}, "
                f"expected {kc.SCHEME_ID!r}"
            )
        return AdapterResult(
            adapter_id=self.id,
            attempted=True,
            applied=True,
            verified=not errors,
            supported=True,
            errors=tuple(errors),
        )

    def rollback(self, previous_state, context) -> AdapterResult:
        errors: list[str] = []
        warnings: list[str] = []
        journal = Journal.load(journal_path(context.state_root))

        if journal.path and not any(
            (journal.scheme_existed, journal.profile_path)
        ):
            return AdapterResult(
                adapter_id=self.id,
                rolled_back=True,
                warnings=("no konsole journal record; nothing to revert",),
            )

        # 1. restore profile key / bytes
        if journal.profile_path:
            profile = Path(journal.profile_path)
            try:
                if journal.profile_snapshot:
                    rolled, warns = adapter_support.restore_snapshot(profile, journal.profile_snapshot)
                    warnings.extend(warns)
                    if not rolled:
                        errors.extend(warns)
                elif profile.is_file():
                    text = profile.read_text(encoding="utf-8")
                    restored = _unset_profile_key(text) if not journal.profile_key_existed else (
                        _set_profile_key_value(text, journal.profile_color_scheme_prev or "")
                    )
                    atomic_write_text(profile, restored)
            except (OSError, AdapterError) as exc:
                errors.append(f"cannot revert konsole profile: {exc}")

        # 2. remove our generated colorscheme if we created it
        if not journal.scheme_existed:
            try:
                scheme = self.environment().profiles_dir / kc.SCHEME_FILENAME
                scheme.unlink(missing_ok=True)
            except OSError as exc:
                errors.append(f"cannot remove {kc.SCHEME_FILENAME}: {exc}")
        elif journal.scheme_snapshot:
            scheme = self.environment().profiles_dir / kc.SCHEME_FILENAME
            rolled, warns = adapter_support.restore_snapshot(scheme, journal.scheme_snapshot)
            warnings.extend(warns)
            if not rolled:
                errors.extend(warns)

        return AdapterResult(
            adapter_id=self.id,
            rolled_back=not errors,
            warnings=tuple(warnings),
            errors=tuple(errors),
        )


# ---------------------------------------------------------------------------
# profile INI surgery (byte-preserving outside the one key)
# ---------------------------------------------------------------------------

def parse_profile_entries(text: str) -> dict[tuple[str, str], str]:
    from adapters.konsole.detection import parse_ini

    return parse_ini(text)


def _set_profile_key(text: str, value: str) -> tuple[str, str | None, bool]:
    """Set ``[Appearance] ColorScheme=<value>``, preserving all other bytes.

    Returns ``(new_text, previous_value_or_None, key_existed)``.
    """
    entries = parse_profile_entries(text)
    previous = entries.get(("Appearance", "ColorScheme"))

    group_match = _APPEARANCE_GROUP.search(text)
    line_re = re.compile(r"^(ColorScheme\s*=.*)$", re.MULTILINE)
    if group_match:
        start = group_match.end()
        next_group = re.search(r"^\[", text[start:], re.MULTILINE)
        end = start + (next_group.start() if next_group else len(text[start:]))
        block = text[start:end]
        if line_re.search(block):
            new_block = line_re.sub(f"ColorScheme={value}", block, count=1)
            return text[:start] + new_block + text[end:], previous, True
        stripped_block = block.rstrip("\n")
        new_block = (
            (stripped_block + "\n" if stripped_block else "") + f"ColorScheme={value}\n"
        )
        return text[:start] + new_block + text[end:], previous, False

    # No [Appearance] group yet: append it at the end of the file.
    prefix = "" if text.endswith("\n") or not text else "\n"
    return f"{text}{prefix}[Appearance]\nColorScheme={value}\n", previous, False


def _set_profile_key_value(text: str, value: str) -> str:
    new_text, _, _ = _set_profile_key(text, value)
    return new_text


def _unset_profile_key(text: str) -> str:
    """Remove the ColorScheme line inside [Appearance]; keep other keys."""
    group_match = _APPEARANCE_GROUP.search(text)
    if not group_match:
        return text
    start = group_match.end()
    next_group = re.search(r"^\[", text[start:], re.MULTILINE)
    end = start + (next_group.start() if next_group else len(text[start:]))
    block = text[start:end]
    cleaned = re.sub(r"^ColorScheme\s*=.*\n?", "", block, flags=re.MULTILINE)
    return text[:start] + cleaned + text[end:]
