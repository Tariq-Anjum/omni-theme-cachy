# Troubleshooting

Start with the two read-only diagnostics:

```bash
omni doctor --json | jq .        # environment, binaries, capabilities
omni status --json | jq .        # runtime state consistency
```

`doctor` always exits 0 and never writes. `status` exits `CONFLICT` (11)
when pointers and `state.json` disagree.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 2 | bad arguments / refused confirmation (write command without `--yes` on non-TTY) |
| 10 | theme validation failed |
| 11 | runtime state inconsistent |
| 12 | requested capability unavailable |
| 13 | apply/preview could not complete |
| 14 | rollback could not complete |
| 20 | unexpected engine failure |

## "refusing to proceed without --yes (non-interactive shell)"

Write commands (`theme apply`, `theme rollback`, `wallpaper set`) ask for
confirmation on a TTY and require `--yes` otherwise. Nothing happened;
re-run with `--yes`.

## "conflict: <path> diverged from the engine's last-written content"

You hand-edited (or another tool rewrote) a file Omni manages — most
often `~/.local/share/color-schemes/OmniTheme.colors`. Omni refuses to
overwrite user content silently.

* Preferred: don't edit the generated file; edit the
  [template/overlay](OVERRIDES.md) that produces it.
* Or reclaim the file with `omni theme apply <theme> --force` — every
  forced overwrite is reported as a warning.

Check `omni doctor --json | jq .managed_target_conflicts` for the
authoritative list.

## "no previous generation recorded … nothing to roll back to"

There is no `previous` slot (first activation, or it was consumed by an
earlier rollback). Rollback is one step, ping-pong style — see
[ROLLBACK.md](ROLLBACK.md).

## Rollback restored an older look than I expected

Rollback re-applies the recorded previous *generation* — not manual
changes you made in System Settings afterwards. `kdeglobals` is KDE's
state; Omni only re-applies its own scheme package. To leave the manual
choice in place, don't roll back; simply `omni theme apply <theme> --yes`
to move forward to a known generation instead.

## Theme applies but apps don't repaint

* Color Scheme: running Qt/Plasma apps repaint via KDE's own
  notifications. If `plasma-apply-colorscheme` failed, the apply outcome
  is `DEGRADED` with the tool's stderr in `errors`/`warnings` — run
  `omni theme apply <theme> --yes --json | jq .adapter_results`.
* Plasma style (panel/OSD chrome): **not themed by Omni** (separate KDE
  concept — see `../architecture/qt-kde-boundary.md`).
* GTK apps: partial by nature; see [GTK.md](GTK.md).
* Konsole: ensure Konsole is the terminal and it has a default profile;
  without one the adapter reports unsupported with that reason.

## "no Plasma session detected"

The KDE adapter needs a live Plasma session or the plasma tools present
(`omni doctor` shows both). Applying still works for file-only targets
(color scheme package, editor/terminal files) — the desktop-apply steps
are skipped and reported, and the outcome is `DEGRADED`, never half-done.

## `status` says inconsistent / exit code 11

Pointers and `state.json` disagree (e.g. a generation directory was
deleted by hand). `status.details` names the mismatched link. Recover by
re-activating a theme (`omni theme apply <theme> --yes`), which writes a
consistent generation — or clear the state root
(`~/.local/state/omni-theme/`) and start fresh. Omni never edits user
config to "fix" this.

## Polluted XDG_STATE_HOME

If a third-party tool exports `XDG_STATE_HOME` to something unexpected
(observed on this machine with `~/.config/ai.opencode.desktop`), Omni
honors it at call time and will keep state there. `omni doctor --json |
jq .xdg_directories` shows what is in effect. Run with
`env -u XDG_STATE_HOME omni …` to use the standard `~/.local/state`.

## Themes not found

`omni` searches the `themes/` directory relative to your working
directory by default; pass `--root` explicitly (e.g.
`omni theme list --root ~/.local/share/omni-theme/themes`). References
resolve by directory name, then `theme.id`, then `theme.name`.

## Reporting bugs

Include `omni version`, `omni doctor --json`, `omni status --json` and
the failing command's `--json` output (they contain no personal data
beyond file paths). Repo: <https://github.com/Tariq-Anjum/omni-theme-cachy>.
