# Session 11 — GTK Integration: Respect KDE's Native Synchronization

> Read `raw/00_AGENT_EXECUTION_CONTRACT.md` and `raw/00_PROJECT_MANIFEST.json` first — each exactly once. If output appears truncated, do NOT re-read; proceed with what you have or report BLOCKED naming the exact problem.

## Objective

Correct the GTK behavior using the current KDE Plasma 6 architecture. This session replaces the earlier naive proposal of making GTK files read-only.

KDE already owns a synchronization chain:

    Color Scheme -> kdeglobals -> kde-gtk-config -> GTK theme colors

Therefore Omni must avoid a fight between two configuration authorities. The GTK adapter's default behavior is **detect + verify + report**, not independent overwrite.

## OpenCode tools

Use: read, glob, grep, bash, edit, write, websearch, webfetch.
Free/open-source utilities: rg, fd, python, pytest, git.

## Step 1 — Discovery

Search the existing implementation:

    rg -n "gtk-2|gtk-3|gtk-4|gtkrc|colors.css|gtk.css|kde-gtk-config|kdeglobals" core adapters hooks tests docs

Read every matched implementation file, including `adapters/gtk/` (built in Session 6) and the KDE color-scheme application flow in `adapters/kde/`.

## Step 2 — Determine ownership

The implementation must distinguish:
1. Omni-owned generated color scheme
2. KDE-owned `kdeglobals` state
3. KDE's GTK-sync output
4. User-owned GTK customization

Do not mark all GTK files as Omni-owned.

## Step 3 — Capability detection

Create or extend `adapters/gtk/capability.py`. Return structured capability:

    @dataclass(frozen=True)
    class GTKCapability:
        gtk3_detected: bool
        gtk4_detected: bool
        kde_gtk_sync_detected: bool
        breeze_gtk_detected: bool
        direct_css_supported: bool
        reason: str | None

Detection must not modify files. Treat the live system as ground truth, not documentation claims; `kde_gtk_sync_detected` is true only if the `kde-gtk-config` mechanism is actually present on this system.

## Step 4 — Prefer KDE-native sync

When KDE color-scheme application succeeds, the GTK adapter should detect + verify + report rather than independently overwrite GTK files. If the user configured a non-Breeze GTK theme, report that exact boundary.

## Step 5 — Direct writes (conditional)

Implement direct GTK file writes only if testing in the current environment proves KDE sync cannot satisfy a required supported use case. If implemented:
- Choose an explicitly owned target.
- Record its hash.
- Detect external changes.
- Never chmod to read-only by default.
- Do not automatically disable KDE services without an explicit user action.
- Document persistence risk.
- Route every such write through Session 8's validated atomic write path (approved roots + ownership policy). Do not bypass it.

## Step 6 — CLI diagnostics

`omni doctor --json` must report:

    {
      "adapter": "gtk",
      "supported": true,
      "mode": "kde-native-sync",
      "gtk3": true,
      "gtk4": true,
      "notes": []
    }

or an accurate unsupported result.

## Step 7 — Tests (code + unit; always runnable)

Create:
- tests/unit/test_gtk_capability.py
- tests/unit/test_gtk_ownership.py
- tests/integration/test_gtk_kde_sync.py

Tests:
- No GTK
- GTK present
- KDE GTK sync present
- Non-Breeze GTK theme
- Direct write disabled
- Direct write supported (if implemented)
- Ownership conflict
- Repeat detection

Do not claim a test proves persistence across session start unless it actually exercises logout/login or an equivalent isolated KDE session. If Session 6's existing GTK tests encode the old direct-write behavior, update them to the new model; do not weaken them.

## Step 8 — Real-KDE verification (requires a live KDE session)

This step is the session's explicitly authorized real-desktop verification. On the real target:
- Apply the Omni color scheme.
- Inspect KDE's UI.
- Inspect `~/.config/kdeglobals`.
- Inspect the GTK-related files.
- Verify theme persistence; record exact observations.

Logout safety: do NOT log out if it would interrupt this agent session. If persistence across login cannot be verified safely, record it as "not verified" and proceed. Never log out to satisfy a test.

No-KDE fallback: if no live KDE session is available, mark all real-KDE claims as unverified and proceed with the code and tests from Steps 1–7. Do not wait or retry.

## Exit condition

GTK behavior must be explicitly one of:
- KDE-native sync
- Directly supported
- Unsupported with a documented reason

There must be no silent "works until next login" behavior.

## STOP / BLOCKED

Report BLOCKED and do not guess if:
- `adapters/gtk` or the KDE color-scheme application flow is missing and cannot be inspected.
- Detection contradicts the documented model and you cannot determine the truth from the live system.
- Implementing direct writes would require bypassing Session 8's security path.
- The control plane and the code conflict and no higher-authority rule resolves it.

Do not invent a workaround silently.

## Completion

On PASS:
1. Update `raw/00_PROJECT_MANIFEST.json`: set `current_baseline` to "Session 11 completed", update `status`, remove `11` from `next_sessions`.
2. Update the README control-plane baseline line to Session 11.
3. Commit per AGENTS.md, then `git pull --rebase origin main`, then push.

## Commit

    git add adapters/gtk tests docs raw/00_PROJECT_MANIFEST.json README.md
    git commit -m "fix: align GTK integration with KDE native theme synchronization"
