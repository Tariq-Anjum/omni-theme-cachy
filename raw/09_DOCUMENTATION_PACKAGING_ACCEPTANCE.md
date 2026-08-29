# Session 09 — Documentation, Packaging, Acceptance, and Clean Release Candidate

> Read `00_AGENT_EXECUTION_CONTRACT.md` and `00_PROJECT_MANIFEST.json` first — each exactly once. If output appears truncated, do NOT re-read; proceed or report BLOCKED naming the exact problem.

## Objective

Make the repository understandable, installable, testable, and honest about its capabilities. This session is not "done because documentation exists." It is done only when documented commands match the actual implementation and real KDE behavior.

## OpenCode tools

Use: read, glob, grep, bash, edit, write, lsp.
Use free/open-source tools: rg, fd, jq, python, pytest, git.

## 1. Discovery

Run:
    git status --short
    git log --oneline --decorate -30
    find . -maxdepth 3 -type f | sort

Read: README.md, pyproject.toml, AGENTS.md, docs/research/*, docs/architecture/*, docs/user/*.

## 2. Required architecture docs

Create/complete:
- docs/architecture/ARCHITECTURE.md
- docs/architecture/THEME_MODEL.md
- docs/architecture/ADAPTERS.md
- docs/architecture/ACTIVATION.md
- docs/architecture/OWNERSHIP_AND_SECURITY.md
- docs/architecture/DIVERGENCE_FROM_OMARCHY.md

Use Mermaid where it materially clarifies the design. Base every claim on the actual code or on docs/research/*. Do not invent Omarchy, Hyprland, or Quickshell details that are not grounded in docs/research/ or the repo; if a comparison cannot be grounded, label it "inspiration, not verified."

## 3. Required user docs

Create/complete:
- docs/user/GETTING_STARTED.md
- docs/user/CREATING_THEMES.md
- docs/user/OVERRIDES.md
- docs/user/ROLLBACK.md
- docs/user/TROUBLESHOOTING.md
- docs/user/CLI.md
- docs/user/GTK.md
- docs/user/OPTIONAL_KWIN_SCRIPTS.md

Document unsupported features explicitly.

## 4. Omarchy divergence

Document borrowed architectural ideas: semantic palette, template-driven rendering, user customization, staged theme generation, atomic-ish state promotion, CLI ergonomics, non-interactive `--yes`, agent discoverability.

Document what is NOT borrowed: Hyprland, Quickshell, QML shell, Omarchy shell plugin manifest system, Hyprland IPC, shell layout replacement.

Note: current Omarchy Quattro theming shows theme staging, user theme overlays, user-wide templates, semantic `colors.toml`, and `shell.toml` surface/style roles; those ideas inspire the theme-generation layer. Its Quickshell shell is a separate system. Ground all of this in docs/research/; do not cite unverifiable sources.

## 5. Config directory and precedence

Document `~/.config/omni-theme/` and explicitly explain precedence:

    built-in theme
      < user theme overlay
      < user template override
      < explicit target policy

Do not accidentally imply that Omni duplicates Omarchy's `shell.json`.

## 6. Packaging

Verify pyproject.toml contains a normal executable entry point: `omni`.
Use an isolated virtual environment for testing.
Do not require `sudo pip install ...`.
Do not require global package installation.

## 7. Default theme

Verify `themes/default/` contains: `theme.toml`, `colors.toml`, `surfaces.toml`, `wallpapers/`.
If any of these are missing, report BLOCKED and list exactly what is missing. Do not invent placeholder theme data or artwork.
Do not ship copyrighted artwork. Use generated/simple assets or clearly licensed assets.

## 8. Acceptance run

First confirm every documented command and flag actually exists in the CLI (including `--yes`, e.g. `omni theme apply --help`). If a documented command or flag does not exist, fix the docs to match reality or report the gap; do not claim it works.

Run:
    python -m pytest
    python -m compileall core adapters
    omni theme list
    omni theme validate default
    omni theme preview default --json
    omni theme current --json
    omni status --json
    omni doctor --json

If a KDE session is available and `--yes` exists:
    omni theme apply default --dry-run --json
    omni theme apply default --yes
    omni theme current --json
    omni status --json
    omni theme rollback --yes

This apply→rollback pair is the session's explicitly authorized real-desktop verification. Only claim KDE success if actually observed.
If `--yes` is not yet implemented (it is introduced in Session 14), skip the apply/rollback verification, mark it "not yet verifiable — requires Session 14 `--yes`," and proceed. Do not invent the flag.
If no KDE session is available, mark all KDE claims as unverified and proceed. Do not wait or retry.

## 9. Repository hygiene

Check:
    git status --short
    git diff
    git diff --check

Ensure: no secrets, no personal runtime state, no caches, no broken symlinks, no temporary artifacts.

## Exit condition

The repo is: installable in an isolated environment; documented; tested; honest about unsupported integrations; safe to hand to the post-Session-09 reconciliation phase.

## STOP / BLOCKED

Report BLOCKED and do not guess if:
- `themes/default` is missing a required file and you would have to invent it.
- A documented command or flag does not exist and you cannot determine the truth.
- The control plane and the code conflict and no higher-authority rule resolves it.

Do not invent a workaround silently.

## Completion

On PASS:
1. Update `raw/00_PROJECT_MANIFEST.json`: set `current_baseline` to "Session 9 completed", update `status`, remove `9` from `next_sessions`.
2. Update the README control-plane baseline line to Session 09.
3. Commit per AGENTS.md, then `git pull --rebase origin main`, then push.

## Commit

    git add README.md docs pyproject.toml tests
    git commit -m "docs: complete architecture, user documentation, and acceptance baseline"
