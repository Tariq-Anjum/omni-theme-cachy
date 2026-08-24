# AGENTS.md

## Git workflow

- Canonical repo root: `omni-theme-cachy/` (not the parent `Theme/` folder).
- Remote: `origin` = https://github.com/Tariq-Anjum/omni-theme-cachy.git (branch `main`).
- At the end of every session: commit all work with a conventional message
  (`feat:`, `fix:`, `chore:`, `docs:`), then `git pull --rebase origin main`,
  then `git push`. Standing authorization from the user.
- Never commit: `.venv/`, `state/`, `staging/`, `current/`, build artifacts
  (see `.gitignore`).
- Auth: GitHub CLI at `~/.local/bin/gh`, logged in as Tariq-Anjum; git HTTPS
  credentials handled via `gh auth setup-git`.
