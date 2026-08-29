#!/usr/bin/env python3
"""List candidate direct filesystem writes for manual review (AST scan).

**Reviewer assistance only.** An AST hit does not prove a vulnerability,
and a clean report does not prove safety: static analysis cannot see
dataflow, indirection (``getattr``/``operator``/aliases), or runtime
generated paths. The authoritative guarantee is the central policy in
``core/filesystem.py`` — ``validate_write_target`` (containment,
symlink resolution, ownership policy) enforced inside ``atomic_write`` /
``atomic_copy`` — plus the review table in
``docs/architecture/OWNERSHIP_AND_SECURITY.md``.

Every candidate printed here must be traceable to one of:

* the central policy itself (``core/filesystem.py`` internals);
* a controlled engine-private staging/state directory (pointer
  switches, generation promotion, temp cleanup) whose names are
  schema-checked before use;
* a documented dev-asset tool (``scripts/generate_default_wallpaper.py``
  writes repo assets, never user configuration);
* a native system operation with its own contract (adapter subprocesses
  — out of scope for a filesystem-write scan).

The script excludes itself from its own scan. Exit code is always 0:
this is a review aid, not a gate.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

#: Attribute/method names that create, replace, delete or alter files.
WRITE_ATTRS = {
    "write_text",
    "write_bytes",
    "unlink",
    "mkdir",
    "makedirs",
    "rmdir",
    "rmtree",
    "symlink",
    "link",
    "rename",
    "replace",
    "copyfile",
    "copy2",
    "copytree",
    "copyfileobj",
    "touch",
    "chmod",
    "truncate",
    "fdopen",
    "mkstemp",
    "mkdtemp",
}

#: Module-level function names (``os.*``, ``tempfile.*``, ``shutil.*``…)
#: treated the same as attribute calls above. Plain ``open()`` is handled
#: separately by mode inspection.
WRITE_FUNCS = {
    "unlink",
    "mkdir",
    "makedirs",
    "remove",
    "removedirs",
    "rename",
    "renames",
    "replace",
    "symlink",
    "link",
    "truncate",
    "chmod",
    "fdopen",
    "mkstemp",
    "mkdtemp",
    "copyfile",
    "copy2",
    "copytree",
    "copyfileobj",
    "rmtree",
}

#: ``open()`` mode characters that mean "will write".
OPEN_WRITE_CHARS = {"w", "a", "x", "+"}

SCAN_ROOTS = ("core", "adapters", "hooks", "scripts")


def _describe_call(node: ast.Call) -> str | None:
    """Human-readable name of the called object, or None when unknown."""
    func = node.func
    if isinstance(func, ast.Attribute):
        base = ""
        if isinstance(func.value, ast.Name):
            base = f"{func.value.id}."
        elif isinstance(func.value, ast.Attribute):
            base = f"<attr>.{func.value.attr}."
        return f"{base}{func.attr}"
    if isinstance(func, ast.Name):
        return func.id
    return None


def _open_mode_writes(node: ast.Call) -> bool:
    """True for ``open(...)`` calls whose mode argument can write."""
    for arg in node.args[1:2]:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return bool(OPEN_WRITE_CHARS & set(arg.value))
    for kw in node.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            value = kw.value.value
            if isinstance(value, str):
                return bool(OPEN_WRITE_CHARS & set(value))
    return False  # default mode "r": not a write


def scan_file(path: Path) -> list[tuple[int, str]]:
    """Return ``(lineno, call)`` candidates for one file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return [(getattr(exc, "lineno", 0) or 0, f"<syntax error: {exc}>")]

    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _describe_call(node)
        if name is None:
            continue
        attr = name.rsplit(".", 1)[-1]
        if name == "open" or name.endswith(".open"):
            if _open_mode_writes(node):
                hits.append((node.lineno, f"{name}(mode w/a/x)"))
            continue
        if name in WRITE_ATTRS or attr in WRITE_ATTRS or name in WRITE_FUNCS:
            hits.append((node.lineno, name))
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (default: script's parent's parent)",
    )
    args = parser.parse_args(argv)

    self_path = Path(__file__).resolve()
    total = 0
    for root in SCAN_ROOTS:
        root_dir = args.root / root
        if not root_dir.is_dir():
            continue
        for py_file in sorted(root_dir.rglob("*.py")):
            if py_file.resolve() == self_path:
                continue  # the audit script does not scan itself
            for lineno, call in scan_file(py_file):
                rel = py_file.relative_to(args.root)
                print(f"{rel}:{lineno}: {call}")
                total += 1

    print(
        f"\n{total} candidate write site(s) under "
        f"{', '.join(SCAN_ROOTS)} — manual review against the central "
        "policy required (see docs/architecture/OWNERSHIP_AND_SECURITY.md)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
