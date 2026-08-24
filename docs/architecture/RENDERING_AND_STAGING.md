# Rendering, Targets, and Staging — omni-theme-cachy (Session 03)

Reference for the template language, the explicit target registry, user
overrides, and the staging pipeline. Implementation: `core/renderer.py`,
`core/targets.py`, `core/staging.py`, `core/filesystem.py`,
`load_theme_with_overlay()` in `core/theme_loader.py`.

## Template language

Templates are inert UTF-8 text; rendering is pure substitution over a
closed helper set — no code execution is possible from a template file.

| Expression | Output |
|---|---|
| `{{ key }}` | palette role or surface value (`accent`, `popups.background`) |
| `{{ key_strip }}` | hex digits without `#` (`4f9eea`) |
| `{{ key_rgb }}` | decimal channels (`79, 158, 234`) |
| `{{ mix A B T }}` | blend B over A by T → `#rrggbb` |
| `{{ mix_strip A B T }}` | blend → hex digits without `#` |
| `{{ mix_rgb A B T }}` | blend → decimal channels |
| `{{ kde_gradient REF }}` | surfaces gradient → Qt/QSS `qlineargradient(…)` |

* Mix operands may be keys **or** literal `#RRGGBB` colors. Ratios accept
  `0.2`, `20`, and `"20%"` interchangeably.
* An explicitly defined key always wins over suffix decomposition
  (defining a role literally named `foo_rgb` shadows the `foo` +
  `_rgb` filter).
* Rendering is **strict**: unknown variables, malformed helpers,
  unclosed `{{`, and empty output fail loudly with template name, line
  number and the offending expression. Nothing ever silently expands to
  an empty string.

### kde_gradient semantics

Takes a surface reference holding an Omarchy gradient string (e.g.
`controls.focus-border = "rgba(4f9eeaee) rgba(8f6cafee) 45deg"`) and
emits Qt Style Sheet syntax:

```
qlineargradient(x1:0, y1:1, x2:1, y2:0, stop:0 rgba(79, 158, 234, 93%), stop:1 rgba(143, 108, 175, 93%))
```

Angles follow the CSS convention (clockwise, `0deg` = to top); multiples
of 45° snap to canonical corner geometry, other angles use exact
trigonometry through the box center; a missing angle defaults to
top→bottom. Stop positions are evenly distributed; alpha is emitted as a
percentage, which Qt and CSS interpret identically.

## Template resolution order

For each logical template *name* (its path in the registry), highest
precedence first — first existing file wins (Omarchy rule):

1. `~/.config/omni-theme/templates/<name>` — user override
2. `<theme>/templates/<name>` — theme-specific
3. `templates/<name>` — built-in (repo tree indexed by `targets.toml`)

## User overlays (Omarchy pattern)

```
Base:    themes/<theme>/colors.toml + surfaces.toml
Overlay: ~/.config/omni-theme/themes/<theme>/colors.toml + surfaces.toml
```

The overlay deep-merges over the base key-by-key: color roles replace or
add roles; surface entries replace at `(group, key)` granularity while
sibling keys survive. `[theme]` metadata and wallpaper always stay with
the base theme — users tweak values, never identity. Overlay files may
contain only what is being tweaked; a missing overlay directory is not
an error.

## Explicit targets registry (`templates/targets.toml`)

The engine never infers destinations from filenames. Every rendered
artifact is declared:

```toml
[[template]]
adapter = "kde-colorscheme"            # optional, informational

[template.source]
path = "kde/OmniTheme.colors.tpl"      # relative to templates/, must end .tpl

[template.target]
path = "~/.local/share/color-schemes/OmniTheme.colors"
```

Validation is strict (`core/targets.py`): unknown keys anywhere, missing
tables, relative or `..`-containing paths, non-`.tpl` sources, missing
source files, duplicate sources and duplicate targets are hard errors.
The shipped registry starts empty (`template = []`) until the KDE
adapter session fills it.

## Runtime directories

All XDG variables are honored at call time (`$XDG_CONFIG_HOME`,
`$XDG_DATA_HOME`, `$XDG_STATE_HOME`):

```
~/.config/omni-theme/    user overlays, user templates   (config)
~/.local/share/omni-theme/                               (data)
~/.local/state/omni-theme/
├── current/             promoted, active snapshot
├── previous/            rollback source
├── staging/             clean rebuild every run
└── backups/             timestamped slots for displaced dirs
```

## Staging pipeline

```
resolve → load → merge user overlays → validate → render
        → validate generated files → stage → manifest.json
```

Every application renders into a pristine `staging/` (leftovers from an
aborted run are wiped first). Nothing outside `staging/` — and
especially nothing live on the desktop or under `current/` — is touched
during staging. Promotion happens later via atomic rename
(`promote_directory()`: old dir → timestamped backup slot, staging →
current; each step one same-filesystem rename).

## Atomic writes

`core.filesystem.atomic_write`: create parent dirs safely → write
sibling temp file → flush → fsync → apply permissions (explicit mode,
else preserve existing file's mode, else 0644) → `os.replace`.
Failures remove the temp file and leave the destination untouched.

## Manifest (`manifest.json`, written into staging)

```json
{
  "version": 1,
  "theme":   {"name": "...", "id": "...", "version": 1, "mode": "dark"},
  "theme_source": "/path/to/theme",
  "timestamp": "2026-08-24T12:00:00+00:00",
  "ownership": "base | user-overlay",
  "files": [
    {"name": "kde/X.tpl", "source": "/abs/tpl", "origin": "user|theme|builtin",
     "target": "/abs/dest", "adapter": null, "hash": "<sha256>", "staged": "kde/X"}
  ]
}
```

`hash` is the SHA-256 of the rendered bytes; it doubles as the managed
hash for conflict detection.

## Ownership and conflicts

The engine owns only what it generated. Before modifying a previously
managed target, its current hash is compared against the hash recorded
in the last manifest:

* equal → safe to update;
* different (hand-edited, replaced by another tool) → reported as a
  conflict, never silently overwritten;
* absent → fresh install, no conflict.

An explicit force/override switch arrives with the CLI session.
