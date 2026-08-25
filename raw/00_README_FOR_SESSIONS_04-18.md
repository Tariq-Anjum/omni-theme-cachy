# Omni Theme Engine — Revised Sessions 04–18

These files assume **Session 03 is already complete**.

The sequence deliberately moves corrections discovered during the original 9-session design and the post-Session-09 handover into the earliest session where they can be handled safely.

## Order

| Session | Focus |
|---|---|
| 04 | Activation state, atomic promotion, rollback, adapter contract |
| 05 | KDE Plasma 6 Color Scheme + wallpaper |
| 06 | GTK, VS Code, terminal application adapters |
| 07 | CLI, doctor, preview, status, JSON |
| 08 | Security, path policy, ownership, failure injection |
| 09 | Documentation, packaging, acceptance |
| 10 | Reconcile with real Omarchy Quattro |
| 11 | KDE-native GTK synchronization |
| 12 | Path/symlink safety coverage |
| 13 | KDE INI/config safety |
| 14 | `--yes`, JSON, `omni commands` |
| 15 | One-command installer + CI |
| 16 | KWin scope hygiene |
| 17 | OpenCode commands/tools/permissions |
| 18 | Final verification and release |

## Key corrections integrated

- Omarchy is treated as an architectural reference, not a KDE compatibility target.
- `surfaces.toml` remains an Omni semantic model; it is not claimed to be a copy of Omarchy shell configuration.
- KDE Color Scheme, Plasma Style, and Global Theme remain separate capabilities.
- GTK does not default to chmod-444 file ownership; KDE-native synchronization is preferred.
- Adapter failures are separated from unsupported adapters.
- All external writes require centralized path/ownership policy.
- KDE INI files are not modified through naive string appends.
- Every mutating CLI command has a consistent `--yes` convention.
- Machine-readable CLI output has schema versions.
- OpenCode project commands use `.opencode/commands/`; custom tools use `.opencode/tools/`.
- Release claims must distinguish implemented, tested, real-KDE-verified, unsupported, and unverified.