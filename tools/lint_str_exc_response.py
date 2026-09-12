#!/usr/bin/env python
"""Reject ``str(exc)`` on a caught exception inside a view or serializer.

django_notes.md's ViewSet standards say never put ``str(exc)`` in a response,
and CodeQL flags the same shape as `py/stack-trace-exposure`: the string form of
an exception is how a stack frame, a SQL error or an internal path reaches a
response body by accident. Today's exception may carry authored copy; the next
one, or a subclass raised deeper in, may not.

The fix is not to sanitise the string. It is for the exception to carry the
player-facing sentence as an explicit attribute the view reads by name, so
nothing derived from the exception's own representation is ever serialised.

Flags ``str(name)``/``f"{name}"`` where *name* is bound by ``except ... as
name`` in the enclosing function. CodeQL catches the taint path in CI; this
catches the instance at commit time, which is cheaper.

Suppress with ``# noqa: STR_EXC`` and say why.
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys

NOQA_CODE = "STR_EXC"


class Visitor(ast.NodeVisitor):
    def __init__(self, path: Path, lines: list[str]) -> None:
        self.path = path
        self.lines = lines
        self.caught: set[str] = set()
        self.problems: list[tuple[int, str]] = []

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        added = None
        if node.name:
            added = node.name
            self.caught.add(node.name)
        self.generic_visit(node)
        if added is not None:
            self.caught.discard(added)

    def _flag(self, lineno: int, name: str) -> None:
        line = self.lines[lineno - 1] if lineno - 1 < len(self.lines) else ""
        if f"noqa: {NOQA_CODE}" in line:
            return
        self.problems.append(
            (
                lineno,
                f"str({name}) on a caught exception: give the exception an explicit "
                f"player-facing attribute and read that instead",
            )
        )

    def visit_Call(self, node: ast.Call) -> None:
        if (
            isinstance(node.func, ast.Name)
            and node.func.id == "str"
            and len(node.args) == 1
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id in self.caught
        ):
            self._flag(node.lineno, node.args[0].id)
        self.generic_visit(node)

    def visit_FormattedValue(self, node: ast.FormattedValue) -> None:
        if isinstance(node.value, ast.Name) and node.value.id in self.caught:
            self._flag(node.lineno, node.value.id)
        self.generic_visit(node)


def check(path: Path) -> list[str]:
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    visitor = Visitor(path, source.splitlines())
    visitor.visit(tree)
    return [f"{path}:{line}: {message}" for line, message in visitor.problems]


def main(argv: list[str]) -> int:
    failures: list[str] = []
    for name in argv:
        failures.extend(check(Path(name)))
    for failure in failures:
        print(failure)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
