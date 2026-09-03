"""Reject ``.only(...)`` and ``.defer(...)`` querysets on identity-mapped models (ADR-0261).

Every concrete model here is a ``SharedMemoryModel`` (ADR-0008). Its metaclass
answers every construction of a pk with the instance already resident in the
identity map and never copies the freshly-read columns onto it. A row whose
FIRST load in a process went through ``.only(...)``/``.defer(...)`` is therefore
resident with the narrowed columns missing for the life of the process. Django's
deferred-attribute getter then calls ``refresh_from_db(fields=[...])``, gets that
same resident instance back, skips the still-deferred field and raises
``KeyError``. That was Sentry ARX2-9 (2026-09-03): the CG beginnings list
prefetched codex grants with ``.only("beginnings_id", "entry_id")``, and the
Beginnings admin change page 500'd on ``is_perspective`` for everyone until
the server restarted.

Nothing is saved by narrowing, either: the identity map loads a row once and
serves it from memory afterwards. Drop the ``.only``/``.defer``. If a
projection is genuinely wanted (a pk walk, a count), use ``.values()`` or
``.values_list()``, which never instantiate a model and so never touch the
cache.

Use ``# noqa: IDMAPPER_ONLY`` on the call's line to suppress, with a reason. A
queryset over a model that is provably not identity-mapped (a Django or
third-party model) is the only reason that exists.
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys

SUPPRESSION_TOKEN = "noqa: idmapper_only"  # noqa: S105
NARROWING_METHODS = frozenset({"only", "defer"})


def has_suppression(line: str) -> bool:
    """Return whether ``line`` carries the suppression token."""
    return SUPPRESSION_TOKEN in line.lower()


class NarrowingVisitor(ast.NodeVisitor):
    """Collect every ``.only``/``.defer`` call that is not suppressed on its line."""

    def __init__(self, lines: list[str]) -> None:
        super().__init__()
        self.lines = lines
        self.errors: list[tuple[int, int, str]] = []

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in NARROWING_METHODS:
            line_index = max(func.lineno - 1, 0)
            suppressed = line_index < len(self.lines) and has_suppression(self.lines[line_index])
            if not suppressed:
                self.errors.append((func.lineno, func.col_offset, func.attr))
        self.generic_visit(node)


def check_source(source: str) -> list[tuple[int, int, str]]:
    """Return ``(line, col, method)`` for every unsuppressed narrowing call in ``source``."""
    tree = ast.parse(source)
    visitor = NarrowingVisitor(source.splitlines())
    visitor.visit(tree)
    return visitor.errors


def check_file(path: Path) -> list[tuple[int, int, str]]:
    """Return the narrowing-call errors in the file at ``path``."""
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    try:
        return check_source(source)
    except SyntaxError:
        return []


def main(argv: list[str]) -> int:
    """Lint the given files; print each violation and return 1 if any were found."""
    failed = False
    for filename in argv:
        for lineno, col, method in check_file(Path(filename)):
            failed = True
            print(
                f"{filename}:{lineno}:{col + 1}: .{method}() on an identity-mapped model "
                "leaves the row resident with missing columns for the whole process "
                "(KeyError on the next full read). Drop it, or use .values()/.values_list() "
                "for a projection. Suppress with `# noqa: IDMAPPER_ONLY` plus a reason "
                "only for a model that is not a SharedMemoryModel."
            )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
