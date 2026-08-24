"""Exception hierarchy for omni-theme-cachy.

All engine errors derive from ThemeError so callers can catch one base
class. Load errors cover unreadable/malformed theme sources; validation
errors carry structured issues; ColorError signals malformed color data.
"""


class ThemeError(Exception):
    """Base class for all omni-theme-cachy errors."""


class ThemeLoadError(ThemeError):
    """A theme directory or its TOML files could not be read/parsed."""


class ColorError(ThemeError):
    """A color value is not valid ``#RRGGBB`` (or documented ``#RGB``)."""


class SurfaceValueError(ThemeError):
    """A surface-role value is malformed (gradient string, border-width
    list, out-of-range alpha, …).

    Kept separate from :class:`ColorError` because these values are not
    plain colors; both are caught by :class:`ThemeError` handlers.
    """


class ThemeValidationError(ThemeError):
    """Raised when strict validation is requested and issues exist.

    Carries the list of :class:`core.validation.Issue` objects under
    ``issues`` so programmatic consumers get full detail.
    """

    def __init__(self, message: str, issues):
        super().__init__(message)
        self.issues = list(issues)


# --- Session 03: rendering, registries, staging ---------------------------


class RenderError(ThemeError):
    """A template could not be rendered (unknown variable, bad helper
    call, malformed ``{{ … }}`` expression).

    Strict by design: unknown variables never silently expand to empty
    strings, so a typo in a template fails loudly with the template name,
    line number and offending expression.
    """


class TemplateNotFoundError(RenderError):
    """A template name resolved to no file in any search root."""


class TargetsError(ThemeError):
    """The template-targets registry (``templates/targets.toml``) is
    missing, malformed or violates its schema."""


class StagingError(ThemeError):
    """Staging could not be completed (I/O problem, duplicate target,
    render failure during the pipeline)."""


class ManifestError(ThemeError):
    """A manifest.json is missing, unreadable or structurally invalid."""


# --- Session 04: runtime state, activation, adapters -----------------------


class StateError(ThemeError):
    """The runtime state (``state.json`` or the generation layout under
    ``$XDG_STATE_HOME/omni-theme``) is missing, corrupt, inconsistent or
    violates an invariant (bad generation id, non-symlink ``current``,
    …)."""


class ActivationError(ThemeError):
    """An activation invariant was violated (staged output failed its
    integrity check, promotion hit an unexpected layout, …)."""


class ConflictError(ThemeError):
    """A live target file diverged from the hash the engine last wrote
    there, and no explicit force policy was requested."""


class RollbackError(ThemeError):
    """A rollback was requested but cannot be performed (no previous
    generation recorded, or the recorded generation vanished)."""


class AdapterError(ThemeError):
    """An adapter violates the adapter contract (duplicate id registered,
    malformed capability/result, …)."""
