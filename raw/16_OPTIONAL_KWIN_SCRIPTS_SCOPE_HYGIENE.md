# Session 16 — KWin Scope Hygiene and Optional Community Tiling Scripts

## Objective

Explicitly keep window-management behavior outside the core theme engine.

Omni targets:

```text
KDE Plasma 6
KWin
traditional floating-window workflow
mouse-driven desktop usage
```

It must not silently install or enable third-party AUR software.

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
```

## Step 1 — Auto-install audit

Run:

```bash
rg -n "pacman -S|yay -S|paru -S|paru |yay " core adapters hooks scripts install.sh
```

Expected:

```text
no automatic AUR/system package installation
```

Installer dependency checks may tell users how to install prerequisites, but must not silently install them.

## Step 2 — KWin scope audit

Search:

```bash
rg -n "kwin|tiling|krohnkite|kzones|polonium|plasmazones|BorderlessMaximizedWindows" core adapters hooks scripts docs
```

Classify each reference:

```text
theme-related
optional behavior
legacy
unintended
```

Remove unintended tiling/window-management behavior from the core.

## Step 3 — Documentation

Create:

```text
docs/user/OPTIONAL_KWIN_SCRIPTS.md
```

Explain:

> Omni Theme Engine does not install or manage window-tiling behavior.

If documenting community scripts, verify current sources before publication.

Do not imply endorsement or security review.

## Step 4 — Borderless behavior

If the project includes a setting such as:

```text
BorderlessMaximizedWindows
```

ensure it is:

- explicitly opt-in;
- safely parsed;
- reversible;
- documented.

Do not automatically apply window-behavior changes as part of ordinary theme activation.

## Step 5 — Tests

Test:

```text
no package installer invocation
no auto-enabling KWin scripts
KWin config unchanged by normal theme application
optional feature isolated if retained
```

## Exit condition

A normal:

```bash
omni theme apply default --yes
```

does not:

```text
install packages
enable scripts
change tiling behavior
replace KWin
```

## Commit

```bash
git add docs tests core adapters hooks scripts
git commit -m "docs: isolate optional KWin behavior from theme activation"
```