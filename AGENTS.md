# AGENTS.md

Think before acting.
Use the smallest sufficient context.
Do not repeat information already available.
Load capabilities only when required.
Prefer existing tools over explaining how to use them.
Make the smallest correct change.
Verify before declaring success.
Escalate only when evidence requires it.

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
