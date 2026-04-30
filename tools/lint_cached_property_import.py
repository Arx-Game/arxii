"""Reject `from functools import cached_property` in src/.

functools.cached_property silently breaks Django's Prefetch(to_attr=...)
because Django's prefetch machinery only recognizes its own
django.utils.functional.cached_property via isinstance.

See src/evennia_extensions/CACHED_PROPERTY_STANDARD.md for rationale.

Use "# noqa: CACHED_PROPERTY_IMPORT" with a justification to suppress.
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys

SUPPRESSION_TOKEN = "noqa: cached_property_import"  # noqa: S105


def has_suppression(line: str) -> bool:
    """Return whether the source line contains the suppression token.

    Args:
        line: The source line to inspect.

    Returns:
        True when the suppression token is present (case-insensitive).
    """
    return SUPPRESSION_TOKEN in line.lower()


def find_violations(tree: ast.AST, source_lines: list[str]) -> list[tuple[int, str]]:
    """Return (lineno, message) tuples for each violation in the tree.

    Detects two forbidden patterns:
        1. ``from functools import cached_property`` (any aliasing).
        2. ``functools.cached_property`` attribute access — the form
           that follows ``import functools``.

    Args:
        tree: The parsed AST.
        source_lines: The file's source split into lines.

    Returns:
        A list of (lineno, message) violation entries.
    """
    violations: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        # Pattern 1: from functools import cached_property
        if isinstance(node, ast.ImportFrom):
            if node.module != "functools":
                continue
            for alias in node.names:
                if alias.name != "cached_property":
                    continue
                # A multi-line `from functools import (...)` may carry the
                # suppression comment on the alias line rather than on
                # node.lineno. Check every line the import spans.
                start = node.lineno
                end = node.end_lineno or node.lineno
                spanned_lines = source_lines[start - 1 : end]
                if any(has_suppression(line) for line in spanned_lines):
                    continue
                violations.append(
                    (
                        node.lineno,
                        "forbidden import — use 'from django.utils.functional "
                        "import cached_property' (see "
                        "src/evennia_extensions/CACHED_PROPERTY_STANDARD.md)",
                    )
                )
        # Pattern 2: functools.cached_property attribute access
        elif (
            isinstance(node, ast.Attribute)
            and node.attr == "cached_property"
            and isinstance(node.value, ast.Name)
            and node.value.id == "functools"
        ):
            line_index = node.lineno - 1
            if 0 <= line_index < len(source_lines) and has_suppression(source_lines[line_index]):
                continue
            violations.append(
                (
                    node.lineno,
                    "forbidden attribute access — 'functools.cached_property' "
                    "silently breaks Prefetch(to_attr=...). Use Django's "
                    "cached_property instead (see "
                    "src/evennia_extensions/CACHED_PROPERTY_STANDARD.md)",
                )
            )
    return violations


def check_file(path: Path) -> list[tuple[int, str]]:
    """Return violations for a single file.

    Args:
        path: Path to the file to inspect.

    Returns:
        A list of (lineno, message) violation entries.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [(0, f"cannot read ({exc})")]
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        return [(exc.lineno or 0, f"syntax error: {exc.msg}")]
    return find_violations(tree, text.splitlines())


def main(argv: list[str]) -> int:
    """Run the cached_property import check across argv files.

    Args:
        argv: Command-line arguments (file paths to check).

    Returns:
        Exit status code: 1 if any violation found, 0 otherwise.
    """
    exit_code = 0
    for raw_path in argv:
        path = Path(raw_path)
        if path.suffix != ".py":
            continue
        for lineno, message in check_file(path):
            print(f"{path}:{lineno}: CACHED_PROPERTY_IMPORT {message}")
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
