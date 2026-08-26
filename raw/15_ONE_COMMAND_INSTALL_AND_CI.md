# Session 15 — One-Command Install, Isolated Environment, and CI Smoke Test

## Objective

Provide a real end-user installation path for CachyOS/Arch while keeping development installs separate.

The installation system must not require:

```bash
sudo pip install ...
```

and must not modify system Python packages.

## OpenCode tools

Use:

- `read`
- `glob`
- `grep`
- `bash`
- `edit`
- `write`
- `lsp`

Free/open-source:

```bash
git
python
pytest
bash
jq
```

## Step 1 — Inspect packaging

Read:

```text
pyproject.toml
README.md
```

Confirm:

```text
package name
CLI entry point
Python minimum version
dependencies
```

Do not assume the entry point is `omni`.

## Step 2 — Installer requirements

Create:

```text
install.sh
```

It must:

1. run with `set -euo pipefail`;
2. verify `git` and `python`;
3. determine repository/installation path safely;
4. create a dedicated virtual environment;
5. install the project into that environment;
6. expose `omni` through `~/.local/bin`;
7. avoid `sudo`;
8. avoid changing system Python;
9. be idempotent;
10. print a useful post-install path/doctor instruction.

## Step 3 — Safer update semantics

Do not automatically `git pull` over a user's modified installation without detecting changes.

Prefer:

```text
existing install
  -> verify git repo
  -> fetch
  -> fast-forward only
  -> install
```

If local changes exist:

```text
stop
report
do not destroy changes
```

## Step 4 — Installer script

Use:

```bash
#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/Tariq-Anjum/omni-theme-cachy.git"
INSTALL_DIR="${OMNI_INSTALL_DIR:-$HOME/.local/share/omni-theme-cachy}"
BIN_DIR="${OMNI_BIN_DIR:-$HOME/.local/bin}"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    exit 1
  }
}

require_cmd git
require_cmd python

if [ -d "$INSTALL_DIR/.git" ]; then
  if [ -n "$(git -C "$INSTALL_DIR" status --porcelain)" ]; then
    echo "Refusing to update installation with local changes: $INSTALL_DIR" >&2
    exit 1
  fi
  git -C "$INSTALL_DIR" fetch --prune origin
  git -C "$INSTALL_DIR" merge --ff-only origin/main
else
  mkdir -p "$(dirname "$INSTALL_DIR")"
  git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

if [ ! -d .venv ]; then
  python -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install .

mkdir -p "$BIN_DIR"

cat > "$BIN_DIR/omni" <<EOF
#!/usr/bin/env bash
exec "$INSTALL_DIR/.venv/bin/omni" "\$@"
EOF

chmod +x "$BIN_DIR/omni"

echo "Installed omni to $BIN_DIR/omni"
echo "Run: $BIN_DIR/omni doctor"
```

Adapt packaging commands if the project uses another supported installation mechanism.

## Security note

Do not blindly teach users:

```bash
curl | bash
```

as the only method.

Document:

```text
reviewable git clone + installer
one-command convenience form
manual/local install
```

If a curl-pipe command is documented, explain that users may inspect `install.sh` first.

## Step 5 — CI

Create:

```text
.github/workflows/install-smoke-test.yml
```

Use a free/open-source Arch-compatible CI container if GitHub-hosted Actions remains the chosen environment.

Example:

```yaml
name: install-smoke-test

on:
  push:
  pull_request:

jobs:
  smoke:
    runs-on: ubuntu-latest
    container: archlinux:latest
    steps:
      - uses: actions/checkout@v4

      - name: Install prerequisites
        run: pacman -Sy --noconfirm git python

      - name: Run installer
        run: bash install.sh

      - name: Smoke test
        run: |
          export PATH="$HOME/.local/bin:$PATH"
          omni version
          omni theme list
          omni commands --json
```

If the project requires additional build dependencies, install only those explicitly.

## Step 6 — Install tests

Run in a clean temporary HOME when possible:

```bash
tmp_home="$(mktemp -d)"
HOME="$tmp_home" bash install.sh
HOME="$tmp_home" PATH="$tmp_home/.local/bin:$PATH" omni version
```

Do not let the test overwrite the developer's real installation.

## Exit condition

A clean Arch-like environment can install Omni without system Python mutation and execute:

```bash
omni version
omni theme list
omni commands --json
```

## Commit

```bash
git add install.sh .github/workflows/install-smoke-test.yml docs README.md
git commit -m "feat: add isolated one-command installer and Arch smoke test"
```
