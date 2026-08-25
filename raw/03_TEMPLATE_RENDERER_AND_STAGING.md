# Session 03 — Template Renderer, User Overlays, and Staging

## Objective
Implement deterministic template rendering, user overlays, user template precedence, target mappings, atomic staging, manifests, atomic file operations, and conflict detection.

## Prerequisite
Sessions 01–02 complete.

## 1. Implement renderer

Create:
```text
core/renderer.py
core/filesystem.py
```

Support:
```text
{{ key }}
{{ key_strip }}
{{ key_rgb }}
{{ mix ... }}
{{ mix_strip ... }}
{{ mix_rgb ... }}
{{ kde_gradient ... }}
```

Unknown variables must produce a clear, strict error.

Do not silently substitute empty strings.

## 2. User Overlays (Omarchy pattern)

Before rendering, the engine must deep-merge user overrides on top of the base theme:

```text
Base:    themes/<theme>/colors.toml
Overlay: ~/.config/omni-theme/themes/<theme>/colors.toml
```

User colors and surface roles strictly override base values, key by key. This allows a user to tweak one accent color or border without forking the entire theme.

## 3. User Templates (Omarchy pattern)

Template resolution order, highest precedence first:
```text
1. ~/.config/omni-theme/templates/<file>.tpl   (user override)
2. themes/<theme>/templates/<file>.tpl         (theme specific)
3. templates/default/<file>.tpl                (built-in)
```

## 4. Explicit template targets

Do not infer arbitrary target paths from filenames.

Use explicit metadata, for example:
```toml
[source]
path = "templates/kde/OmniTheme.colors.tpl"

[target]
path = "~/.local/share/color-schemes/OmniTheme.colors"
```

Choose the exact project format, document it, and validate it.

## 5. Runtime directories

Use:
```text
~/.config/omni-theme/
~/.local/share/omni-theme/
~/.local/state/omni-theme/
```

Allow XDG/config overrides.

Recommended state:
```text
~/.local/state/omni-theme/
├── current/
├── previous/
├── staging/
└── backups/
```

## 6. Atomic staging

Every theme application must render to a clean staging directory first:
```text
~/.local/state/omni-theme/staging/
```

Pipeline:
```text
resolve
→ load
→ merge user overlays
→ validate
→ render (using resolved template precedence)
→ validate generated files
→ stage
```

Nothing should touch the live desktop or the `current/` directory during staging.

## 7. Manifest

Create:
```text
manifest.json
```

Record:
- source
- target
- adapter
- hash
- theme
- timestamp
- ownership mode (base vs user overlay)

## 8. Atomic writes

Implement safe file replacement.

Requirements:
- create parent directories safely
- preserve permissions where appropriate
- write temporary file
- flush
- atomic rename/replace

## 9. Ownership/conflict detection

Before modifying a previously managed target:
- compare current hash against managed hash
- if unchanged, it is safe to update
- if manually modified, report conflict
- never silently overwrite

Provide an explicit force/override mechanism later through CLI.

## 10. Tests

Create tests for:
- template rendering
- helper expansion
- missing variables
- user overlay merging (base vs overlay precedence)
- user template precedence resolution
- staging
- manifests
- hashes
- atomic replacement
- conflicts
- temporary XDG directories

Never test against the user's real `$HOME`.

Run the complete test suite.

## 11. Commit
```bash
git add .
git commit -m "feat: add template renderer, user overlays, and safe staging"
```

## Exit condition
Stop after staging, user overlays, and conflict-safe file operations are fully tested. No KDE application yet.