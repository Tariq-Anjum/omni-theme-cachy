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
