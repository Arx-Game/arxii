"""Reject bare string literals used as identifiers in returns, comparisons, and match/case.

Use "# noqa: STRING_LITERAL" to suppress a specific instance.
"""

from __future__ import annotations

import ast
from pathlib import Path
import re
import sys

SUPPRESSION_TOKEN = "noqa: string_literal"  # noqa: S105

# Strings matching this pattern are not identifier-like and should be allowed.
SKIP_PATTERN = re.compile(r"[/\\.^$*+?{}\[\]|()\s]")


def is_identifier_string(value: str) -> bool:
    """Return whether a string value looks like a bare identifier.

    Returns False for strings that are clearly not identifiers: empty,
    single-character, underscore-prefixed, or containing path/regex chars.

    Args:
        value: The string value to inspect.

    Returns:
        True when the value looks like a bare identifier constant.
    """
    if len(value) <= 1:
        return False
    if value.startswith("_"):
        return False
    if SKIP_PATTERN.search(value):
        return False
    return True


def has_suppression(line: str) -> bool:
    """Return whether a line suppresses the string literal check.

    Args:
        line: The source line to inspect.

    Returns:
        True when the suppression token is present.
    """
    return SUPPRESSION_TOKEN in line.lower()


class StringLiteralVisitor(ast.NodeVisitor):
    """Visitor that collects bare string literals in returns, comparisons, and match/case."""

    def __init__(self, path: Path, lines: list[str]) -> None:
        super().__init__()
        self.path = path
        self.lines = lines
        self.errors: list[tuple[int, int]] = []

    def _check_constant(self, node: ast.expr) -> None:
        """Check whether a node is a bare string constant and record an error if so.

        Args:
            node: The AST expression node to inspect.
        """
        if not isinstance(node, ast.Constant):
            return
        if not isinstance(node.value, str):
            return
        if not is_identifier_string(node.value):
            return
        line_index = max(node.lineno - 1, 0)
        if line_index < len(self.lines) and has_suppression(self.lines[line_index]):
            return
        self.errors.append((node.lineno, node.col_offset))

    def visit_Return(self, node: ast.Return) -> None:
        """Check return values for bare string literals.

        Args:
            node: The AST return node.
        """
        if node.value is not None:
            self._check_constant(node.value)
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        """Check both sides of comparisons for bare string literals.

        Args:
            node: The AST compare node.
        """
        self._check_constant(node.left)
        for comparator in node.comparators:
            self._check_constant(comparator)
        self.generic_visit(node)

    def visit_MatchValue(self, node: ast.MatchValue) -> None:
        """Check match/case pattern values for bare string literals.

        Args:
            node: The AST match value node.
        """
        self._check_constant(node.value)
        self.generic_visit(node)


def check_file(path: Path) -> list[tuple[int, int]]:
    """Return errors for bare string literals in a file.

    Args:
        path: Path to the file to inspect.

    Returns:
        A list of (line, column) error locations.
    """
    try:
        contents = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"{path}:0:0: STRING_LITERAL could not read file: {exc}")
        return [(0, 0)]

    try:
        tree = ast.parse(contents, filename=str(path))
    except SyntaxError as exc:
        lineno = exc.lineno or 0
        offset = exc.offset or 0
        print(f"{path}:{lineno}:{offset}: STRING_LITERAL syntax error: {exc.msg}")
        return [(lineno, offset)]

    lines = contents.splitlines()
    visitor = StringLiteralVisitor(path, lines)
    visitor.visit(tree)
    return visitor.errors


def main(argv: list[str]) -> int:
    """Run the string literal check.

    Args:
        argv: Command-line arguments.

    Returns:
        Exit status code.
    """
    errors_found = False
    for raw_path in argv:
        path = Path(raw_path)
        if path.suffix != ".py":
            continue
        errors = check_file(path)
        for line, col in errors:
            errors_found = True
            column = col + 1 if col else 0
            print(
                f"{path}:{line}:{column}: STRING_LITERAL "
                "Do not use bare string literals as identifiers. "
                "Use constants (TextChoices, module-level variables) "
                "or add # noqa: STRING_LITERAL."
            )
    return 1 if errors_found else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
