# Session 01 — Foundation and Research

## Objective
Research the environment, upstream Omarchy architecture, and KDE Plasma 6, and establish the architectural foundation. Do not implement the full engine in this session.

## Context boundary
This session is intentionally limited to environment discovery, upstream research, architecture decisions, repository initialization, and project scaffolding.

## Exact execution

### 1. Inspect environment
Run:
```bash
pwd
uname -a
cat /etc/os-release
echo "$XDG_CURRENT_DESKTOP"
echo "$XDG_SESSION_TYPE"
echo "$HOME"
echo "$XDG_CONFIG_HOME"
echo "$XDG_DATA_HOME"
echo "$XDG_STATE_HOME"
plasmashell --version
python --version
git --version
```

Then:
```bash
command -v plasma-apply-colorscheme || true
command -v qdbus || true
command -v qdbus6 || true
command -v kreadconfig6 || true
command -v kwriteconfig6 || true
command -v kbuildsycoca6 || true
```

Record the actual results. Never assume KDE commands exist without verifying.

### 2. Research Omarchy (crucial architectural inputs)
Inspect the current Omarchy theming documentation and source (`basecamp/omarchy` on GitHub).

Research and document:
- Theme directories, `colors.toml`, semantic palette, templates, staging, user themes, user templates, precedence, activation, theme state, color helpers, tests.
- **User Overlays**: how Omarchy merges `~/.config/omarchy/themes/<name>/` over base system themes.
- **User Templates**: how user templates in `~/.config/omarchy/themed/*.tpl` take precedence over built-in templates.
- **Surface Roles (`shell.toml`)**: how Omarchy defines UI controls, borders, alphas, and popups separately from base colors.
- **Staging & Symlinks**: how Omarchy uses `~/.local/state/.../next-theme` and atomic symlinks for zero-downtime switching.

The current documentation describes a clean staging directory, user-theme overlay, user-wide template, and promotion to current state via atomic symlink switching. Preserve those architectural ideas where appropriate. [Source: Omarchy theming documentation]

Create:
```text
docs/research/ENVIRONMENT.md
docs/research/OMARCHY_THEMING.md
docs/research/OMARCHY_ARCHITECTURE.md
```

### 3. Research KDE Plasma 6
Inspect current KDE documentation for:
- Color Schemes
- Plasma Styles
- Global Themes
- Wallpaper mechanisms (DBus vs CLI)
- Plasma 6 packaging
- KWin reload/restart behavior

Important distinction:
- Color Scheme is not the same thing as Plasma Style.
- Plasma 6 theme packages use current KPackage conventions.
- User-installed Plasma themes live under XDG user data locations.

Create:
```text
docs/research/KDE_PLASMA_6.md
```

### 4. Research adjacent projects
Investigate current Linux theming approaches for architectural ideas:
- pywal/wal
- Gradience
- Stylix
- KDE theme tooling
- GTK theme tooling
- existing theme managers

Do not add dependencies merely because another project uses them.

Create:
```text
docs/research/LINUX_THEME_ENGINES.md
```

### 5. Architecture decisions
Write:
```text
docs/research/ARCHITECTURE_DECISIONS.md
```

It must explicitly answer:
- Why TOML?
- Why Python?
- Why a semantic theme model?
- Why adapters?
- Why staging?
- Why atomic activation?
- Why runtime state outside Git?
- How user overrides work?
- How User Overlays merge without breaking base themes?
- How Surface Roles (borders, popups, controls) map to KDE/GTK?
- How file ownership works?
- How rollback works?
- How unsupported integrations behave?
- How third-party themes are prevented from executing arbitrary code?

### 6. Initialize repository
Create:
```text
/mnt/MD/Project/Theme/omni-theme-cachy
```

If it already exists, inspect and preserve it.

Otherwise:
```bash
mkdir -p /mnt/MD/Project/Theme/omni-theme-cachy
cd /mnt/MD/Project/Theme/omni-theme-cachy
git init -b main
git remote add origin https://github.com/Tariq-Anjum/omni-theme-cachy
```

### 7. Create initial structure
Create:
```text
core/
adapters/
themes/
templates/
hooks/
tests/
docs/research/
docs/architecture/
docs/user/
scripts/
```

Add:
```text
pyproject.toml
README.md
LICENSE
.gitignore
```

Only create scaffolding in this session.

### 8. Verify
Run:
```bash
git status
find . -maxdepth 3 -type f | sort
python -m compileall core adapters
```

### 9. Commit
```bash
git add .
git commit -m "chore: initialize project and document Omarchy-inspired architecture"
```

Do not push unless explicitly requested.

## Deliverables
- Environment research
- Omarchy research (including User Overlays, User Templates, Surface Roles, staging & symlinks)
- KDE Plasma 6 research
- Linux theming research
- Architecture decisions
- Repository scaffold
- First Git commit

## Exit condition
Stop after the foundation is committed. Do not begin implementation of the renderer or adapters.