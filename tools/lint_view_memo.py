"""Reject None-defaulted private class attributes on views and serializers (#3597, ADR-0260).

The shape ``_thing: T | None = None`` at class level, filled lazily during a
request so later methods reuse it, is a per-request memo hiding as a class
attribute. It is thread-safe only because DRF builds a fresh view per request,
its state is invisible in every signature, reordering two method calls
silently changes the query count, and the class-level default looks shared.

Data about the account belongs on the ``Account`` typeclass as a
``cached_property`` (identity-mapped, cleared through ``related_cache_fields``).
Data about the request is attached once at the boundary (middleware) or passed
as an explicit argument (a serializer ``context=``). Never stashed on ``self``.

Use ``# noqa: VIEW_MEMO`` on the attribute's line to suppress, with a reason.
The only reason that exists is a class attribute that is genuinely constant
configuration and merely happens to default to None; a memo is never one.
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys

SUPPRESSION_TOKEN = "noqa: view_memo"  # noqa: S105


def has_suppression(line: str) -> bool:
    """Return whether ``line`` carries the suppression token."""
    return SUPPRESSION_TOKEN in line.lower()


def _is_none(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _private_none_default(stmt: ast.stmt) -> tuple[int, int, str] | None:
    """Return ``(line, col, name)`` when ``stmt`` is ``_name[: ann] = None``."""
    if isinstance(stmt, ast.AnnAssign):
        target, value = stmt.target, stmt.value
    elif isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
        target, value = stmt.targets[0], stmt.value
    else:
        return None
    if not isinstance(target, ast.Name) or not target.id.startswith("_"):
        return None
    if target.id.startswith("__") or not _is_none(value):
        return None
    return (stmt.lineno, stmt.col_offset, target.id)


class MemoVisitor(ast.NodeVisitor):
    """Collect every unsuppressed private None-default attribute in a class body."""

    def __init__(self, lines: list[str]) -> None:
        super().__init__()
        self.lines = lines
        self.errors: list[tuple[int, int, str]] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for stmt in node.body:
            hit = _private_none_default(stmt)
            if hit is None:
                continue
            line_index = hit[0] - 1
            if line_index < len(self.lines) and has_suppression(self.lines[line_index]):
                continue
            self.errors.append(hit)
        self.generic_visit(node)


def check_source(source: str) -> list[tuple[int, int, str]]:
    """Return ``(line, col, name)`` for every unsuppressed memo attribute in ``source``."""
    tree = ast.parse(source)
    visitor = MemoVisitor(source.splitlines())
    visitor.visit(tree)
    return visitor.errors


def check_file(path: Path) -> list[tuple[int, int, str]]:
    """Return the memo-attribute errors in the file at ``path``."""
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
        for lineno, col, name in check_file(Path(filename)):
            failed = True
            print(
                f"{filename}:{lineno}:{col + 1}: `{name}` is a None-defaulted private class "
                "attribute, the per-request memo shape ADR-0260 rejects. Account data goes "
                "on the Account typeclass as a cached_property; request data is passed as an "
                "explicit argument or attached by middleware. Suppress with "
                "`# noqa: VIEW_MEMO` plus a reason only for constant configuration."
            )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
