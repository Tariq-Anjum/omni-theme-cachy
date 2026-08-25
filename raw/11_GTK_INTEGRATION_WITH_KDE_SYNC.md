# Session 11 — GTK Integration: Respect KDE's Native Synchronization

## Objective

Correct GTK behavior using current KDE Plasma 6 architecture.

This session replaces the earlier simplistic proposal to make GTK files read-only.

## Current platform fact

KDE's current developer documentation says:

- Color Schemes are user-installed under `~/.local/share/color-schemes/`.
- Applying a Color Scheme copies values into `~/.config/kdeglobals`.
- `kde-gtk-config` automatically synchronizes colors to the Breeze GTK theme, including `~/.config/gtk-3.0/colors.css`. citeturn325344search0

Therefore Omni must avoid a fight between two configuration authorities.

## OpenCode tools

Use:

- `read`
- `glob`
- `grep`
- `bash`
- `edit`
- `write`
- `websearch`
- `webfetch`

Free/open-source utilities:

```bash
rg
fd
python
pytest
git
```

## Step 1 — Audit existing GTK implementation

```bash
rg -n "gtk-2|gtk-3|gtk-4|gtkrc|colors.css|gtk.css|kde-gtk-config|kdeglobals" core adapters hooks tests docs
```

Read every matching implementation.

## Step 2 — Determine ownership

The implementation must distinguish:

```text
1. Omni-owned generated Color Scheme
2. KDE-owned kdeglobals state
3. KDE GTK synchronization output
4. user-owned GTK customizations
```

Do not mark every GTK file as Omni-owned.

## Step 3 — Capability detector

Create or extend:

```text
adapters/gtk/capability.py
```

Return structured capabilities:

```python
@dataclass(frozen=True)
class GTKCapability:
    gtk3_detected: bool
    gtk4_detected: bool
    kde_gtk_sync_detected: bool
    breeze_gtk_detected: bool
    direct_css_supported: bool
    reason: str | None
```

Detection must not mutate files.

## Step 4 — Preferred synchronization model

When KDE Color Scheme application is successful:

```text
KDE Color Scheme
    ->
kdeglobals
    ->
kde-gtk-config
    ->
GTK theme colors
```

The GTK adapter should therefore normally become:

```text
detect + verify + report
```

rather than independently overwriting GTK files.

If the user has configured a non-Breeze GTK theme, report that exact boundary.

## Step 5 — Direct GTK fallback

Only implement direct GTK file writes if current environment testing proves a required supported use case that KDE's synchronization cannot satisfy.

If implemented:

- choose an explicitly owned target;
- record its hash;
- detect external changes;
- never chmod it read-only by default;
- do not disable KDE services automatically without explicit user action;
- document persistence risks.

## Step 6 — CLI diagnostics

`omni doctor --json` must report:

```json
{
  "adapter": "gtk",
  "supported": true,
  "mode": "kde-native-sync",
  "gtk3": true,
  "gtk4": true,
  "notes": []
}
```

or an accurate unsupported result.

## Step 7 — Tests

Create:

```text
tests/unit/test_gtk_capability.py
tests/unit/test_gtk_ownership.py
tests/integration/test_gtk_kde_sync.py
```

Test:

- no GTK
- GTK present
- KDE GTK sync present
- non-Breeze GTK theme
- direct write disabled
- direct write supported, if implemented
- ownership conflict
- repeated detection

Do not claim a test proves session-start persistence unless it actually exercises logout/login or an equivalent isolated KDE session.

## Step 8 — Manual KDE test

On the real target:

1. Apply Omni Color Scheme.
2. Inspect KDE UI.
3. Inspect `~/.config/kdeglobals`.
4. Inspect GTK-related files.
5. Log out/in if safe and practical.
6. Verify whether the theme persists.

Record exact observations.

## Exit condition

GTK behavior is explicitly one of:

```text
KDE-native synchronized
directly supported
unsupported with documented reason
```

There must be no silent "works until next login" behavior.

## Commit

```bash
git add adapters/gtk tests docs
git commit -m "fix: align GTK integration with KDE native theme synchronization"
```