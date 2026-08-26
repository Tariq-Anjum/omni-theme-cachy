# Session 06 — Application Adapters: GTK, VS Code, Terminal, and Safe Capability Boundaries

## Objective

Add application-level integrations while preserving the semantic theme model and the adapter contract.

Priority:

1. KDE-driven GTK synchronization strategy
2. VS Code
3. one explicitly supported terminal
4. Qt/KDE boundary documentation

Do not promise universal application theming.

## Important correction carried forward

Do not blindly generate and own:

```text
~/.config/gtk-4.0/gtk.css
```

as the universal GTK solution.

Current KDE documentation states that applying a KDE Color Scheme updates `~/.config/kdeglobals`, and `kde-gtk-config` synchronizes colors to the Breeze GTK theme, including `~/.config/gtk-3.0/colors.css`. citeturn325344search0

Therefore the preferred architecture is:

```text
Omni semantic theme
      |
      v
KDE Color Scheme
      |
      v
kdeglobals / KDE GTK synchronization
      |
      v
GTK where KDE's native integration supports it
```

Direct GTK file generation is a fallback capability only when research and testing prove it is necessary.

Never make read-only GTK config files the default "fix".

## OpenCode tools

Use:

- `read`
- `glob`
- `grep`
- `bash`
- `edit`
- `write`
- `lsp`
- `websearch`/`webfetch` for current application configuration formats

Free/open-source CLI utilities:

```bash
rg
fd
jq
python
pytest
git
```

## Step 1 — Inventory existing adapters

```bash
find adapters -maxdepth 3 -type f | sort
rg -n "gtk|vscode|Code/User|terminal|Konsole|qt|kdeglobals|gtk-3|gtk-4" adapters core tests
```

Read every adapter file before editing.

Do not create parallel duplicate adapters.

## Step 2 — Common adapter requirements

Every adapter must expose or map to:

```text
id
capability()
plan()
render()
apply()
verify()
rollback()
```

Every adapter returns structured status:

```python
@dataclass(frozen=True)
class AdapterResult:
    adapter_id: str
    supported: bool
    attempted: bool
    applied: bool
    verified: bool
    rolled_back: bool
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
```

Unsupported must not masquerade as failure.

## Step 3 — GTK strategy

Implement detection:

```text
GTK 3 present?
GTK 4 present?
libadwaita apps?
KDE GTK integration present?
Breeze GTK theme?
```

Inspect:

```bash
command -v kcmshell6 || true
command -v kde-gtk-config || true
find ~/.config -maxdepth 2 \( -name 'gtk-3.0' -o -name 'gtk-4.0' \) -print
```

Do not change settings while detecting.

### Preferred behavior

When Omni applies a KDE Color Scheme:

1. verify KDE Color Scheme success;
2. determine whether KDE's GTK synchronization path is active;
3. report GTK capability;
4. avoid fighting KDE by writing the same configuration independently.

### Direct GTK fallback

Only implement direct file generation if required.

If direct generation is used, choose an explicitly owned file and record:

```text
owner = omni
source_generation = ...
previous_hash = ...
```

Never use chmod 444 as the primary ownership strategy.

If a platform service can overwrite the file, either integrate with that service or mark the capability unsupported and tell the user why.

## Step 4 — VS Code

Target:

```text
~/.config/Code/User/settings.json
```

Never replace the whole file.

Use JSON parsing and preserve unrelated settings.

Create a namespaced Omni-owned object.

Recommended pattern:

```json
{
  "workbench.colorCustomizations": {
    "...": "..."
  },
  "_omniTheme": {
    "managed": true,
    "theme": "default",
    "generation": "..."
  }
}
```

If the existing settings schema does not allow a metadata property without affecting VS Code, keep metadata in Omni's own manifest instead and only merge color settings.

Never corrupt or normalize unrelated JSON unless necessary.

## Step 5 — VS Code color mapping

At minimum support:

- terminal ANSI colors
- editor background/foreground
- selection
- widget/popup background
- focus/active controls where VS Code exposes a stable color key

Map from semantic colors and surface roles.

Do not invent VS Code keys.

Add a mapping table and tests.

## Step 6 — Terminal

Choose one terminal based on the actual installed environment.

Candidates:

```text
Konsole
Ghostty
Alacritty
```

Do not implement three terminal formats simultaneously unless the repository already contains robust abstractions.

For Konsole, prefer its documented profile/theme model if it is actually available.

For any chosen terminal:

```text
capability detection
config path discovery
ANSI 16-color mapping
background/foreground mapping
ownership
verify
rollback
```

Do not assume every terminal uses the same INI/TOML format.

## Step 7 — Qt boundary

Document clearly:

```text
Qt application theming
KDE Color Scheme
KDE Plasma Style
KDE Global Theme
```

These are related but not identical.

Only implement documented safe behavior.

## Step 8 — Tests

Create/extend:

```text
tests/unit/test_vscode_adapter.py
tests/unit/test_terminal_adapter.py
tests/unit/test_gtk_adapter.py
tests/integration/test_application_adapters.py
```

Test:

- empty configuration
- existing user configuration
- unrelated settings
- malformed JSON
- repeated application
- rollback
- missing application
- unsupported configuration
- path traversal
- user modification conflict

For GTK, test detection independently from actual desktop integration.

## Step 9 — Real validation

Run:

```bash
pytest -q
python -m compileall core adapters hooks
git diff --check
```

On the KDE workstation:

```bash
omni doctor --json
omni theme preview default --json
omni theme apply default --dry-run --json
```

Only enable real application writes after the dry run reports safe targets.

## Exit condition

Every implemented application adapter:

- has explicit capability boundaries;
- has ownership rules;
- has tests;
- supports verification and rollback or explicitly declares why rollback is unsupported;
- reacts to the core lifecycle without hard-coupling the core engine.

## Commit

```bash
git add adapters tests docs
git commit -m "feat: add safe application adapters for GTK, VS Code, and terminal"
```
