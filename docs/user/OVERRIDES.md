# Overrides — customize without touching the repo

Everything the engine reads has a user-side location under
`~/.config/omni-theme/`. Repo updates never clobber your choices, and
your choices apply across themes where appropriate.

## Precedence (highest wins)

```
built-in theme
  < user theme overlay            ~/.config/omni-theme/themes/<name>/
  < user template override        ~/.config/omni-theme/templates/<name>
  < explicit target policy        templates/targets.toml (repo-declared destinations)
```

Concretely, for one rendered artifact the template itself resolves in
this order (first existing file wins, the Omarchy rule):

1. `~/.config/omni-theme/templates/<name>` — user template override
2. `<theme>/templates/<name>` — theme-tier template
3. `templates/<name>` — built-in (repo, indexed by `templates/targets.toml`)

**Targets are not inferred from filenames.** A rendered file reaches disk
only if `templates/targets.toml` declares that destination — that
registry is the explicit target policy, validated strictly. A user cannot
accidentally (or maliciously) steer output to an undeclared path by
dropping in a template.

## User theme overlay

```
~/.config/omni-theme/themes/<name>/
├── colors.toml     # role = "#RRGGBB" — replaces/adds roles
└── surfaces.toml   # [group] key = value — replaces at (group, key) level
```

* Only put the keys you are tweaking. A missing overlay directory is not
  an error.
* Merging is **deep**: overlay color roles replace or add roles; surface
  entries replace single `(group, key)` pairs while sibling keys survive.
* `[theme]` metadata and the wallpaper always stay with the base theme —
  you tweak values, never identity (to change identity, create a real
  theme; see [CREATING_THEMES.md](CREATING_THEMES.md)).
* The overlay is matched by `theme.id` first, then by the theme's
  directory name.

Example — re-accent `default` only:

```toml
# ~/.config/omni-theme/themes/default/colors.toml
accent            = "#e58a5b"
accent_secondary = "#5ba8e5"
selection        = "#4d3423"
```

`omni theme preview default --json | jq .palette.accent` shows the merged
value before you apply.

## User template override

Place a file with the *logical template name* under
`~/.config/omni-theme/templates/` — the same path used in
`templates/targets.toml` (e.g. `kde/OmniTheme.colors.tpl`). Your version
renders instead of the built-in one, for every theme. This is the
"always add my one line to every generated config" escape hatch.

The template language is closed and inert (no code execution):
`{{ key }}`, `{{ key_strip }}`, `{{ key_rgb }}`, `{{ mix A B T }}`,
`{{ kde_gradient REF }}`. Rendering is strict: unknown variables and
malformed helpers are hard errors naming file, line and expression.

## What is *not* user-overridable

* **Managed-target identity**: the engine writes only destinations
  declared in `templates/targets.toml`, and checks each one's hash
  against its last-written record. Hand-edit a managed file (e.g.
  `~/.local/share/color-schemes/OmniTheme.colors`) and the next apply
  reports a conflict and refuses; `--force` overwrites, with a warning.
  Edit the *template or overlay* instead — that is the supported path.
* **Ownership/journal state** under `~/.local/state/omni-theme/` is
  engine bookkeeping; delete the whole state root to start over, but
  don't hand-edit it.

See also: user overlays are the session-tested, documented mechanism —
the deep-merge semantics are specified in
[`../architecture/RENDERING_AND_STAGING.md`](../architecture/RENDERING_AND_STAGING.md).
