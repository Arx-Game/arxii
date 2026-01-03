"""Reject getattr calls with literal attribute names.

Use "# noqa: GETATTR_LITERAL" to suppress a specific instance.
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys

SUPPRESSION_TOKEN = "noqa: getattr_literal"  # noqa: S105
MIN_GETATTR_ARGS = 2


def has_suppression(line: str) -> bool:
    """Return whether a line suppresses the getattr literal check.

    Args:
        line: The source line to inspect.

    Returns:
        True when the suppression token is present.
    """
    return SUPPRESSION_TOKEN in line.lower()


def is_getattr_call(node: ast.Call) -> bool:
    """Return whether a call node is a getattr invocation.

    Args:
        node: The AST call node.

    Returns:
        True when the call targets the builtin getattr.
    """
    return isinstance(node.func, ast.Name) and node.func.id == "getattr"


def literal_attribute_arg(node: ast.Call) -> ast.Constant | None:
    """Return the literal attribute argument, if present.

    Args:
        node: The AST call node.

    Returns:
        The attribute argument constant, or None when unavailable.
    """
    if len(node.args) < MIN_GETATTR_ARGS:
        return None
    attr_arg = node.args[1]
    if isinstance(attr_arg, ast.Constant) and isinstance(attr_arg.value, str):
        return attr_arg
    return None


class GetattrLiteralVisitor(ast.NodeVisitor):
    """Visitor that collects getattr calls with literal attribute names."""

    def __init__(self, path: Path, lines: list[str]) -> None:
        super().__init__()
        self.path = path
        self.lines = lines
        self.errors: list[tuple[int, int]] = []

    def visit_Call(self, node: ast.Call) -> None:
        if is_getattr_call(node):
            attr_arg = literal_attribute_arg(node)
            if attr_arg is not None:
                line_index = max(attr_arg.lineno - 1, 0)
                if line_index < len(self.lines) and has_suppression(self.lines[line_index]):
                    return
                self.errors.append((attr_arg.lineno, attr_arg.col_offset))
        self.generic_visit(node)


def check_file(path: Path) -> list[tuple[int, int]]:
    """Return errors for getattr literals in a file.

    Args:
        path: Path to the file to inspect.

    Returns:
        A list of (line, column) error locations.
    """
    try:
        contents = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"{path}:0:0: GETATTR_LITERAL could not read file: {exc}")
        return [(0, 0)]

    try:
        tree = ast.parse(contents, filename=str(path))
    except SyntaxError as exc:
        lineno = exc.lineno or 0
        offset = exc.offset or 0
        print(f"{path}:{lineno}:{offset}: GETATTR_LITERAL syntax error: {exc.msg}")
        return [(lineno, offset)]

    lines = contents.splitlines()
    visitor = GetattrLiteralVisitor(path, lines)
    visitor.visit(tree)
    return visitor.errors


def main(argv: list[str]) -> int:
    """Run the getattr literal check.

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
                f"{path}:{line}:{column}: GETATTR_LITERAL "
                "Do not call getattr with a literal attribute name. "
                "Use attribute access or add # noqa: GETATTR_LITERAL."
            )
    return 1 if errors_found else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
