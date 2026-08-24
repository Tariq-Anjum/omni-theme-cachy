"""The KDE Plasma 6 adapter: Color Scheme + wallpaper, nothing more.

Scope boundary (session 05)
---------------------------
This adapter deliberately covers exactly two surfaces:

1. **Color Scheme** — generate ``OmniTheme.colors`` (via the core
   template pipeline, so it is a managed target with conflict
   detection and rollback for free), install it by running
   ``plasma-apply-colorscheme``, verify via kdeglobals read-back.
2. **Wallpaper** — validate → cache → apply via native tool → verify
   by reading the active wallpaper back from Plasma.

It does **not** touch Plasma Style, Global Theme, kdeglobals directly,
window decorations or panels. Those are separate adapters by design:
a Color Scheme is an INI palette for Qt/Plasma apps; a Plasma Style
packages SVG shell chrome; a Global Theme bundles several components.
Collapsing them would make precise theming impossible.

Lifecycle mapping
-----------------
``capability`` pure probe · ``plan`` read-only intent · ``render``
read-only artifact check · ``apply`` external side effects · ``verify``
read-back confirmation · ``rollback`` restore previous desktop state.

kdeglobals ownership
--------------------
Applying a Color Scheme makes KDE copy its values into
``~/.config/kdeglobals`` — that file is *KDE user state*, never an
Omni-generated artifact. The only file this adapter lets the engine own
is the generated scheme package under ``$XDG_DATA_HOME/color-schemes/``.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

from core.adapters import AdapterCapability, AdapterResult
from core.errors import AdapterError

from adapters.kde import colors as kde_colors
from adapters.kde.config import (
    SCHEME_ID,
    journal_path,
    run_command,
    safe_scheme_id,
    scheme_file_path,
)
from adapters.kde.detection import (
    TOOL_KREADCONFIG6,
    TOOL_PLASMA_APPLY_COLORSCHEME,
    TOOL_PLASMA_APPLY_WALLPAPERIMAGE,
    PlasmaEnvironment,
    detect_plasma,
)
from adapters.kde.wallpaper import (
    Journal,
    WallpaperBackend,
    cache_path_for,
    ensure_cached,
    sniff_image_format,
)

__all__ = ["KdeAdapter", "KdePlan", "WALLPAPER_CACHE_DIRNAME"]

WALLPAPER_CACHE_DIRNAME = "wallpaper-cache"


@dataclass(frozen=True)
class KdePlan:
    """Everything one activation will do, computed before touching anything."""

    scheme_id: str
    #: Destination of the generated .colors file (core-managed target).
    scheme_path: Path
    #: True when the core manifest really owns that destination.
    scheme_managed_by_core: bool
    #: Theme identity used for wallpaper journal bookkeeping.
    theme_label: str = "omni"
    wallpaper_source: Path | None = None
    wallpaper_cache: Path | None = None
    fill_mode: str | None = None
    surface_report: tuple[kde_colors.SurfaceMapping, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "scheme_id": self.scheme_id,
            "scheme_path": str(self.scheme_path),
            "scheme_managed_by_core": self.scheme_managed_by_core,
            "theme_label": self.theme_label,
            "wallpaper_source": str(self.wallpaper_source) if self.wallpaper_source else None,
            "wallpaper_cache": str(self.wallpaper_cache) if self.wallpaper_cache else None,
            "fill_mode": self.fill_mode,
            "surface_report": [
                {"surface": r.surface, "mode": r.mode, "reason": r.reason}
                for r in self.surface_report
            ],
            "warnings": list(self.warnings),
        }


class KdeAdapter:
    """Applies Omni palettes to KDE Plasma 6 (colorscheme + wallpaper).

    All I/O goes through injectable seams (*env*, *which*, *runner*),
    so unit tests exercise every phase hermetically on machines without
    KDE.
    """

    id = "kde"

    def __init__(
        self,
        *,
        env: Mapping[str, str] | None = None,
        which: Callable[[str], str | None] | None = shutil.which,
        runner: Callable[[list[str]], object] | None = None,
        version_runner: Callable[[list[str]], str | None] | None = None,
    ) -> None:
        self._env = env
        self._which = which
        self._runner = runner
        self._version_runner = version_runner
        # Detection result cached per instance so plan/apply/verify agree
        # on one view of the machine within an activation.
        self._detected: PlasmaEnvironment | None = None

    # -- detection -----------------------------------------------------------

    def environment(self) -> PlasmaEnvironment:
        if self._detected is None:
            kwargs: dict = {}
            if self._env is not None:
                kwargs["env"] = self._env
            if self._which is not None:
                kwargs["which"] = self._which
            if self._version_runner is not None:
                kwargs["version_runner"] = self._version_runner
            self._detected = detect_plasma(**kwargs)
        return self._detected

    def _tools(self) -> dict[str, str | None]:
        return dict(self.environment().tools)

    def _backend(self) -> WallpaperBackend:
        tools = self._tools()
        if self._runner is not None:
            return WallpaperBackend(tools=tools, runner=self._runner)
        return WallpaperBackend(tools=tools)

    def _run(self, argv: list[str]):
        if self._runner is not None:
            return self._runner(argv)
        return run_command(argv)

    # -- contract phases -------------------------------------------------------

    def capability(self, context) -> AdapterCapability:
        env = self.environment()
        if not env.is_plasma_session and env.plasmashell_version is None:
            return AdapterCapability(
                id=self.id,
                supported=False,
                reason="no KDE Plasma session detected "
                f"(XDG_CURRENT_DESKTOP={env.desktop!r}, plasmashell not found)",
            )
        missing = [
            name
            for name in (TOOL_PLASMA_APPLY_COLORSCHEME, TOOL_KREADCONFIG6)
            if not env.has(name)
        ]
        if missing:
            return AdapterCapability(
                id=self.id,
                supported=False,
                reason="missing required tools: " + ", ".join(missing),
            )
        version = env.plasmashell_version
        if env.major_version is not None and env.major_version < 6:
            version = env.plasmashell_version  # reported, still supported
        return AdapterCapability(id=self.id, supported=True, version=version)

    def plan(self, resolved_theme, context) -> KdePlan:
        theme = resolved_theme
        scheme_id = safe_scheme_id(SCHEME_ID)
        scheme_path = scheme_file_path(scheme_id)

        managed = any(
            Path(entry.target).expanduser() == scheme_path
            for entry in context.manifest.files
        )

        warnings: list[str] = []
        wallpaper_source: Path | None = None
        resolved_wp = theme.resolve_wallpaper() if theme.path else None
        if resolved_wp is not None:
            if resolved_wp.is_file():
                try:
                    sniff_image_format(resolved_wp)
                    wallpaper_source = resolved_wp
                except AdapterError as exc:
                    warnings.append(f"theme wallpaper ignored: {exc}")
            else:
                warnings.append(f"theme wallpaper missing on disk: {resolved_wp}")

        cache: Path | None = None
        if wallpaper_source is not None:
            if not self.environment().has(TOOL_PLASMA_APPLY_WALLPAPERIMAGE):
                warnings.append(
                    "theme wallpaper cannot be applied: "
                    "plasma-apply-wallpaperimage is not installed"
                )
            else:
                # Predict the cache path only — the copy happens during
                # apply() so plan stays side-effect-free.
                try:
                    cache = cache_path_for(
                        wallpaper_source,
                        _wallpaper_cache_dir(context.state_root),
                        theme_label=theme.meta.id,
                    )
                except (AdapterError, OSError) as exc:
                    warnings.append(f"theme wallpaper ignored: {exc}")

        report = kde_colors.surface_mapping_report(
            dict(theme.surfaces.items()) if theme.surfaces else None
        )
        return KdePlan(
            scheme_id=scheme_id,
            scheme_path=scheme_path,
            scheme_managed_by_core=managed,
            theme_label=theme.meta.id,
            wallpaper_source=wallpaper_source,
            wallpaper_cache=cache,
            surface_report=report,
            warnings=tuple(warnings),
        )

    def render(self, resolved_theme, generation_dir, context) -> None:
        """Read-only: confirm our artifact actually reached the generation."""
        hint = scheme_file_path(safe_scheme_id(SCHEME_ID))
        for entry in context.manifest.files:
            if Path(entry.target).expanduser() == hint:
                staged = Path(generation_dir) / entry.staged
                if not staged.is_file():
                    raise AdapterError(
                        f"color scheme artifact missing from generation: {staged}"
                    )
                return

    def apply(self, plan: KdePlan, context) -> AdapterResult:
        errors: list[str] = []
        warnings: list[str] = list(plan.warnings)

        if not plan.scheme_managed_by_core:
            errors.append(
                f"no managed color-scheme target for {plan.scheme_path}; "
                "register it in templates/targets.toml"
            )
        elif not plan.scheme_path.is_file():
            errors.append(
                f"color scheme file was not installed at {plan.scheme_path}; "
                "core materialization did not run?"
            )
        else:
            proc = self._run(
                [
                    self.environment().tool_path(TOOL_PLASMA_APPLY_COLORSCHEME),
                    plan.scheme_id,
                ]
            )
            code = getattr(proc, "returncode", 1)
            output = (
                (getattr(proc, "stdout", "") or "")
                + (getattr(proc, "stderr", "") or "")
            ).strip()
            if code != 0:
                errors.append(
                    f"plasma-apply-colorscheme {plan.scheme_id} failed "
                    f"(exit {code}): {output}"
                )
            elif output:
                warnings.append(f"plasma-apply-colorscheme: {output}")

        if plan.wallpaper_cache is not None and plan.wallpaper_source is not None:
            journal = Journal.load(journal_path(context.state_root))
            try:
                # Materialize the cache copy now (apply-time side effect).
                ensure_cached(plan.wallpaper_source, plan.wallpaper_cache)
                backend = self._backend()
                current = backend.current_images()
                journal.remember_pre_omni(current[0] if current else None)
                _backend_name, message = backend.apply_image(plan.wallpaper_cache)
                journal.remember_apply(plan.theme_label, str(plan.wallpaper_cache))
                journal.save()
                if message:
                    warnings.append(f"wallpaper: {message}")
            except AdapterError as exc:
                errors.append(f"wallpaper apply failed: {exc}")

        return AdapterResult(
            adapter_id=self.id,
            attempted=True,
            applied=not errors,
            supported=True,
            warnings=tuple(warnings),
            errors=tuple(errors),
        )

    def verify(self, plan: KdePlan, context) -> AdapterResult:
        errors: list[str] = []

        # 1. the generated package still matches the model
        theme = context.theme
        surfaces = dict(theme.surfaces.items()) if theme is not None and theme.surfaces else None
        palette = dict(theme.palette.colors) if theme is not None else {}
        try:
            installed = plan.scheme_path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"cannot read installed scheme {plan.scheme_path}: {exc}")
        else:
            errors.extend(kde_colors.verify_scheme_text(installed, palette, surfaces))
            general = kde_colors.parse_scheme_text(installed).get(("General", "ColorScheme"))
            if general != plan.scheme_id:
                errors.append(
                    f"[General] ColorScheme is {general!r}, expected {plan.scheme_id!r}"
                )

        # 2. KDE actually selected it (kdeglobals is KDE's own state: read-only)
        kread = self.environment().tool_path(TOOL_KREADCONFIG6)
        if kread:
            proc = self._run(
                [kread, "--file", "kdeglobals",
                 "--group", "General", "--key", "ColorScheme"]
            )
            selected = (getattr(proc, "stdout", "") or "").strip()
            code = getattr(proc, "returncode", 1)
            if code != 0:
                errors.append(f"kreadconfig6 could not read kdeglobals (exit {code})")
            elif selected != plan.scheme_id:
                errors.append(
                    f"kdeglobals General.ColorScheme is {selected!r}, "
                    f"expected {plan.scheme_id!r}: plasma-apply-colorscheme "
                    "did not take effect"
                )

        # 3. the wallpaper survives verification: read the live value back
        if plan.wallpaper_cache is not None:
            try:
                images = self._backend().current_images()
            except AdapterError as exc:
                errors.append(f"cannot read back active wallpaper: {exc}")
            else:
                expected_uri = plan.wallpaper_cache.resolve().as_uri()
                if not any(url == expected_uri for url in images):
                    errors.append(
                        f"active wallpaper does not match cached theme image "
                        f"{expected_uri} (found: {images or 'nothing'})"
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
        env = self.environment()
        if not env.has(TOOL_PLASMA_APPLY_COLORSCHEME):
            return AdapterResult(
                adapter_id=self.id,
                rolled_back=False,
                supported=False,
                errors=("plasma-apply-colorscheme missing; cannot re-apply "
                        "the restored scheme"),
            )
        errors: list[str] = []
        warnings: list[str] = []

        # Core rollback already restored the previous generation's bytes
        # for the managed .colors target; re-apply it so the desktop follows.
        proc = self._run([env.tool_path(TOOL_PLASMA_APPLY_COLORSCHEME), SCHEME_ID])
        if getattr(proc, "returncode", 1) != 0:
            errors.append("could not re-apply restored color scheme")

        # Restore wallpaper state. Preference order: the wallpaper of the
        # generation being restored (by theme id), the most recent other
        # entry, then the recorded pre-Omni original. Plain image URLs
        # only; anything else is left untouched and reported.
        journal = Journal.load(journal_path(context.state_root))
        target_theme = getattr(context.manifest, "theme_id", None)
        previous = journal.wallpaper_for(target_theme)
        if previous is not None:
            previous_path = _as_local_path(previous)
            tool = env.tool_path(TOOL_PLASMA_APPLY_WALLPAPERIMAGE)
            if previous_path is None:
                warnings.append(
                    f"previous wallpaper {previous!r} is not a local image "
                    "path; leaving current wallpaper in place"
                )
            elif tool:
                proc = self._run([tool, str(previous_path)])
                if getattr(proc, "returncode", 1) != 0:
                    errors.append(f"could not restore previous wallpaper {previous}")
            else:
                warnings.append(
                    "cannot restore wallpaper: plasma-apply-wallpaperimage missing"
                )

        return AdapterResult(
            adapter_id=self.id,
            rolled_back=not errors,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _as_local_path(value: str) -> Path | None:
    """Accept a ``file://`` URI or an absolute path; anything else → None.

    The journal mixes both forms on purpose: read-back produces URIs,
    cache bookkeeping uses plain paths.
    """
    parsed = urlparse(value)
    if parsed.scheme == "file":
        return Path(unquote(parsed.path))
    if parsed.scheme:  # https:, sftp:, … cannot be handed to native tools
        return None
    candidate = Path(value)
    return candidate if candidate.is_absolute() else None


def _wallpaper_cache_dir(state_root: Path) -> Path:
    """Omni-owned cache root derived from the engine state root."""
    return Path(state_root) / "adapters" / WALLPAPER_CACHE_DIRNAME


def standalone_wallpaper_cache_dir() -> Path:
    """Cache dir when driving wallpapers outside a full activation."""
    from core.filesystem import omni_state_dir

    return omni_state_dir() / "adapters" / WALLPAPER_CACHE_DIRNAME
