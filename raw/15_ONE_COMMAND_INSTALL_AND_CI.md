# Session 15 — One-Command Install, Isolated Environment, and CI Smoke Test

> Read `raw/00_AGENT_EXECUTION_CONTRACT.md` and `raw/00_PROJECT_MANIFEST.json` first — each exactly once. If output appears truncated, do NOT re-read; proceed with what you have or report BLOCKED naming the exact problem.

## Objective

Provide a real end-user installation path for CachyOS/Arch while keeping development installs separate. The installation system must not require `sudo pip install ...` and must not modify system Python packages.

## Resolved facts — read before implementing

The manifest records three decisions for this session:
- installer = `install.sh` (checkout or managed clone → dedicated venv → `pip install .` → `~/.local/bin` shim)
- build_command = none (pure-Python project; `pip install .` needs no build step)
- CI provider = GitHub Actions with an archlinux container

Do not re-open these decisions.

## OpenCode tools

Use: read, glob, grep, bash, edit, write, lsp.
Free/open-source utilities: git, python, pytest, bash, jq.

## Step 1 — Inspect packaging

Read:
- pyproject.toml
- README.md

Confirm: package name, CLI entry points (`omni` and `omni-theme`), Python minimum version, dependencies. Do not assume the entry point is `omni` — verify it.

## Step 2 — Create install.sh

It must:
- run with `set -euo pipefail`;
- verify `git` and `python` exist, and that the interpreter satisfies pyproject's `requires-python`;
- determine repository/installation path safely;
- create a dedicated virtual environment;
- install the project into that environment via `pip install .`;
- expose `omni` AND `omni-theme` through `~/.local/bin`;
- avoid `sudo`;
- avoid changing system Python;
- be idempotent;
- print a useful post-install PATH/doctor instruction.

Two source modes, both required:
1. **Managed clone (default, end user):** no source specified — clone or update `$REPO_URL` into `$INSTALL_DIR`.
2. **Local source (development and CI):** `OMNI_SOURCE_DIR=<repo checkout>` — install from that checkout. Never clone, never modify the checkout's git state.

Reference shape:

    #!/usr/bin/env bash
    set -euo pipefail
    REPO_URL="https://github.com/Tariq-Anjum/omni-theme-cachy.git"
    INSTALL_DIR="${OMNI_INSTALL_DIR:-$HOME/.local/share/omni-theme-cachy}"
    BIN_DIR="${OMNI_BIN_DIR:-$HOME/.local/bin}"

    require_cmd() {
      command -v "$1" >/dev/null 2>&1 || { echo "Missing required command: $1" >&2; exit 1; }
    }
    require_cmd git
    require_cmd python

    if [ -n "${OMNI_SOURCE_DIR:-}" ]; then
      SRC_DIR="$OMNI_SOURCE_DIR"
    else
      SRC_DIR="$INSTALL_DIR"
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
    fi

    cd "$SRC_DIR"
    if [ ! -d .venv ]; then
      python -m venv .venv
    fi
    .venv/bin/python -m pip install --upgrade pip
    .venv/bin/python -m pip install .
    mkdir -p "$BIN_DIR"
    cat > "$BIN_DIR/omni" <<EOF
    #!/usr/bin/env bash
    exec "$SRC_DIR/.venv/bin/omni" "\$@"
    EOF
    cat > "$BIN_DIR/omni-theme" <<EOF
    #!/usr/bin/env bash
    exec "$SRC_DIR/.venv/bin/omni-theme" "\$@"
    EOF
    chmod +x "$BIN_DIR/omni" "$BIN_DIR/omni-theme"
    echo "Installed omni to $BIN_DIR/omni"
    echo "Run: $BIN_DIR/omni doctor"

Adapt packaging commands only if pyproject reveals another supported installation mechanism.

## Step 3 — Safer update semantics

Do not automatically `git pull` over a user-modified installation without detecting changes. Prefer:

    existing install -> verify git repo -> fetch -> fast-forward only -> install

If local changes exist: stop, report, do not destroy changes.

## Step 4 — CI smoke test

Create: `.github/workflows/install-smoke-test.yml` using GitHub Actions with an Arch-compatible container. The smoke test MUST install the commit under test, not `origin/main` — use the local-source mode against the checkout:

    name: install-smoke-test
    on: [push, pull_request]
    jobs:
      smoke:
        runs-on: ubuntu-latest
        container: archlinux:latest
        steps:
          - uses: actions/checkout@v4
          - name: Install prerequisites
            run: pacman -Sy --noconfirm git python
          - name: Run installer
            run: OMNI_SOURCE_DIR="$GITHUB_WORKSPACE" bash install.sh
          - name: Smoke test
            run: |
              export PATH="$HOME/.local/bin:$PATH"
              omni version
              omni theme list
              omni commands --json

If the project requires additional build dependencies, install only those explicitly.

## Step 5 — Install tests

Run in a clean temporary HOME when possible:

    tmp_home="$(mktemp -d)"
    HOME="$tmp_home" bash install.sh
    HOME="$tmp_home" PATH="$tmp_home/.local/bin:$PATH" omni version

Do not let the test overwrite the developer's real installation. Tests use temp fixtures only.

## Step 6 — Security documentation

Do not blindly teach users `curl | bash` as the only method. Document:
- reviewable git clone + installer
- one-command convenience form
- manual/local install

If a curl-pipe command is documented, explain that users may inspect `install.sh` first.

## Step 7 — Run

    pytest -q
    git diff --check
    HOME="$(mktemp -d)" bash install.sh
    HOME=<same temp> PATH=<temp>/.local/bin:$PATH omni version

## Exit condition

A clean Arch-like environment can install Omni without system Python mutation and execute:

    omni version
    omni theme list
    omni commands --json

The CI smoke test installs the commit under test, not origin/main.

## STOP / BLOCKED

Report BLOCKED and do not guess if:
- pyproject.toml does not define the expected entry points or minimum Python version.
- Installing in an isolated venv fails for a dependency reason that would require adding or changing dependencies.
- The CI environment cannot run the installer and you cannot determine why.
- The control plane and the code conflict and no higher-authority rule resolves it.

Do not invent a workaround silently.

## Completion

On PASS:
1. Update `raw/00_PROJECT_MANIFEST.json`: set `current_baseline` to "Session 15 completed", update `status`, remove `15` from `next_sessions`.
2. Update the README control-plane baseline line to Session 15.
3. Commit per AGENTS.md, then `git pull --rebase origin main`, then push.

## Commit

    git add install.sh .github/workflows/install-smoke-test.yml docs README.md raw/00_PROJECT_MANIFEST.json
    git commit -m "feat: add isolated one-command installer and Arch smoke test"
