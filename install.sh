#!/usr/bin/env bash
# Omni Theme Cachy — one-command installer.
#
# Installs omni (and the omni-theme alias) into a dedicated virtual
# environment with no sudo and no changes to system Python.
#
# Source modes:
#   1. Managed clone (default, end user):
#        clone or update $REPO_URL into $INSTALL_DIR, then install.
#   2. Local source (development and CI):
#        OMNI_SOURCE_DIR=/path/to/checkout bash install.sh
#      Installs from that checkout. Never clones; never modifies the
#      checkout's git state.
#
# Environment overrides:
#   OMNI_INSTALL_DIR  managed-clone location (default ~/.local/share/omni-theme-cachy)
#   OMNI_BIN_DIR      shim location        (default ~/.local/bin)
#   OMNI_SOURCE_DIR   install from this checkout instead of a managed clone
#
# Idempotent: safe to re-run; an existing managed installation is
# fast-forwarded only when it is clean.

set -euo pipefail

REPO_URL="https://github.com/Tariq-Anjum/omni-theme-cachy.git"
INSTALL_DIR="${OMNI_INSTALL_DIR:-$HOME/.local/share/omni-theme-cachy}"
BIN_DIR="${OMNI_BIN_DIR:-$HOME/.local/bin}"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "Missing required command: $1" >&2; exit 1; }
}

require_cmd git
require_cmd python

# "Determine the installation path safely": an empty or relative HOME
# would resolve INSTALL_DIR/BIN_DIR to nonsense locations.
if [ -z "$HOME" ] || [ "${HOME#/}" = "$HOME" ]; then
  echo "Refusing to install: HOME must be an absolute, non-empty path (got: '$HOME')" >&2
  exit 1
fi

if [ -n "${OMNI_SOURCE_DIR:-}" ]; then
  # Local-source mode: development and CI.
  SRC_DIR="$OMNI_SOURCE_DIR"
  if [ ! -f "$SRC_DIR/pyproject.toml" ]; then
    echo "OMNI_SOURCE_DIR is not a project checkout (no pyproject.toml): $SRC_DIR" >&2
    exit 1
  fi
else
  # Managed-clone mode: end user.
  SRC_DIR="$INSTALL_DIR"
  if [ -d "$INSTALL_DIR/.git" ]; then
    if [ -n "$(git -C "$INSTALL_DIR" status --porcelain)" ]; then
      echo "Refusing to update installation with local changes: $INSTALL_DIR" >&2
      echo "Resolve or remove the changes in that clone, then re-run." >&2
      exit 1
    fi
    git -C "$INSTALL_DIR" fetch --prune origin
    git -C "$INSTALL_DIR" merge --ff-only origin/main
  else
    if [ -e "$INSTALL_DIR" ]; then
      echo "Refusing to overwrite non-clone installation directory: $INSTALL_DIR" >&2
      echo "Set OMNI_INSTALL_DIR to a fresh location, or use OMNI_SOURCE_DIR." >&2
      exit 1
    fi
    mkdir -p "$(dirname "$INSTALL_DIR")"
    git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
  fi
fi

cd "$SRC_DIR"

if [ ! -f pyproject.toml ]; then
  echo "pyproject.toml not found in: $SRC_DIR" >&2
  exit 1
fi

# The interpreter must satisfy pyproject's requires-python before any
# environment is created. tomllib (Python 3.11+) reads the requirement,
# so an interpreter that is too old fails here with a clear message.
python - <<'PYCHECK'
import re
import sys

try:
    import tomllib
except ModuleNotFoundError:
    sys.stderr.write(
        "error: Python %d.%d lacks tomllib; omni-theme-cachy requires "
        "Python 3.11+ (pyproject requires-python)\n" % sys.version_info[:2]
    )
    sys.exit(1)

with open("pyproject.toml", "rb") as fh:
    spec = tomllib.load(fh)["project"]["requires-python"]


def version_tuple(text):
    parts = text.strip().split(".")
    if not all(part.isdigit() for part in parts):
        raise ValueError("unsupported version: %r" % text)
    return tuple(int(part) for part in parts)


def satisfies(have, op, want):
    width = max(len(have), len(want))
    have = have + (0,) * (width - len(have))
    want = want + (0,) * (width - len(want))
    return {
        ">=": have >= want,
        ">": have > want,
        "<=": have <= want,
        "<": have < want,
        "==": have == want,
        "!=": have != want,
    }[op]


have = version_tuple(".".join(str(part) for part in sys.version_info[:3]))
for clause in spec.split(","):
    match = re.fullmatch(r"\s*(>=|<=|==|!=|>|<)\s*(\d+(?:\.\d+)*)\s*", clause)
    if match is None:
        sys.stderr.write(
            "error: cannot evaluate requires-python specifier: %r\n" % spec
        )
        sys.exit(1)
    if not satisfies(have, match.group(1), version_tuple(match.group(2))):
        sys.stderr.write(
            "error: Python %s does not satisfy requires-python %s\n"
            % (".".join(str(part) for part in have), spec)
        )
        sys.exit(1)
PYCHECK

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

echo
echo "Installed omni to $BIN_DIR/omni"
echo "Installed omni-theme to $BIN_DIR/omni-theme"
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
  echo
  echo "NOTE: $BIN_DIR is not on your PATH. Add it, e.g.:"
  echo "  echo 'export PATH=\"$BIN_DIR:\$PATH\"' >> ~/.bashrc   # then: source ~/.bashrc"
fi
echo
echo "Next steps:"
echo "  $BIN_DIR/omni doctor        # read-only environment diagnostic"
echo "  $BIN_DIR/omni version"
echo "  $BIN_DIR/omni theme list    # themes are found under ./themes (cwd) or via --root"
