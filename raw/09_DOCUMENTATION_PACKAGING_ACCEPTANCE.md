# Session 09 — Documentation, Packaging, Acceptance, and Clean Release Candidate

## Objective

Make the repository understandable, installable, testable, and honest about its capabilities.

This session is not "done because documentation exists." It is done only when documented commands match the actual implementation and real KDE behavior.

## OpenCode tools

Use:

- `read`
- `glob`
- `grep`
- `bash`
- `edit`
- `write`
- `lsp`

Use free/open-source tools:

```bash
rg
fd
jq
python
pytest
git
```

## Step 1 — Read repository state

```bash
git status --short
git log --oneline --decorate -30
find . -maxdepth 3 -type f | sort
```

Read:

```text
README.md
pyproject.toml
AGENTS.md
docs/research/*
docs/architecture/*
docs/user/*
```

## Step 2 — Required architecture docs

Create/complete:

```text
docs/architecture/ARCHITECTURE.md
docs/architecture/THEME_MODEL.md
docs/architecture/ADAPTERS.md
docs/architecture/ACTIVATION.md
docs/architecture/OWNERSHIP_AND_SECURITY.md
docs/architecture/DIVERGENCE_FROM_OMARCHY.md
```

Use Mermaid where it materially clarifies the design.

## Step 3 — Required user docs

Create/complete:

```text
docs/user/GETTING_STARTED.md
docs/user/CREATING_THEMES.md
docs/user/OVERRIDES.md
docs/user/ROLLBACK.md
docs/user/TROUBLESHOOTING.md
docs/user/CLI.md
docs/user/GTK.md
docs/user/OPTIONAL_KWIN_SCRIPTS.md
```

Document unsupported features explicitly.

## Step 4 — Omarchy divergence

Document:

### Borrowed architectural ideas

- semantic palette
- template-driven rendering
- user customization
- staged theme generation
- atomic-ish state promotion
- CLI ergonomics
- non-interactive `--yes`
- agent discoverability

### Not borrowed

- Hyprland
- Quickshell
- QML shell
- Omarchy shell plugin manifest system
- Hyprland IPC
- shell layout replacement

Current Omarchy Quattro's theming docs show theme staging, user theme overlays, user-wide templates, semantic `colors.toml`, and `shell.toml` surface/style roles; those ideas are inspiration for the theme-generation layer. Its Quickshell shell is a separate system. citeturn576446view0turn576446view2

## Step 5 — Theme overrides documentation

Document:

```text
~/.config/omni-theme/
```

and explicitly explain precedence.

Recommended model:

```text
built-in theme
    < user theme overlay
    < user template override
    < explicit target policy
```

Do not accidentally imply that Omni duplicates Omarchy's `shell.json`.

## Step 6 — Packaging

Verify:

```text
pyproject.toml
```

contains a normal executable entry point:

```text
omni
```

Use an isolated virtual environment for testing.

Do not require:

```bash
sudo pip install ...
```

Do not require global package installation.

## Step 7 — Default theme

Verify:

```text
themes/default/
    theme.toml
    colors.toml
    surfaces.toml
    wallpapers/
```

Do not ship copyrighted artwork.

Use generated/simple assets or clearly licensed assets.

## Step 8 — Acceptance test

Run:

```bash
python -m pytest
python -m compileall core adapters

omni theme list
omni theme validate default
omni theme preview default --json
omni theme current --json
omni status --json
omni doctor --json
```

If KDE is available:

```bash
omni theme apply default --dry-run --json
omni theme apply default --yes
omni theme current --json
omni status --json
omni theme rollback --yes
```

Only claim KDE success if actually observed.

## Step 9 — Repository hygiene

Check:

```bash
git status --short
git diff
git diff --check
```

Ensure:

```text
no secrets
no personal runtime state
no caches
no broken symlinks
no temporary artifacts
```

## Exit condition

The repo is:

- installable in an isolated environment;
- documented;
- tested;
- honest about unsupported integrations;
- safe to hand to the post-Session-09 reconciliation phase.

## Commit

```bash
git add README.md docs pyproject.toml tests
git commit -m "docs: complete architecture, user documentation, and acceptance baseline"
```
