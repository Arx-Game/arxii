"""Reject direct query_params/GET access inside ViewSet and View classes.

Use django-filter FilterSet classes instead.
Use "# noqa: USE_FILTERSET" to suppress a specific instance.
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys

SUPPRESSION_TOKEN = "noqa: use_filterset"  # noqa: S105

_VIEW_BASES = {"ViewSet", "View", "APIView"}


def _get_base_name(node: ast.expr) -> str | None:
    """Extract simple name from a base class node.

    Args:
        node: The AST expression node for a base class.

    Returns:
        The simple class name, or None if it cannot be determined.
    """
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return None


def _is_view_class(class_node: ast.ClassDef) -> bool:
    """Return True if any base name contains a VIEW_BASES fragment.

    Args:
        class_node: The AST class definition node.

    Returns:
        True when the class inherits from a view-like base.
    """
    for base in class_node.bases:
        name = _get_base_name(base)
        if name is not None:
            for fragment in _VIEW_BASES:
                if fragment in name:
                    return True
    return False


def _should_skip_file(path: Path) -> bool:
    """Return True if the file should be skipped (test files).

    Args:
        path: Path to the file.

    Returns:
        True when the filename indicates a test file.
    """
    name = path.name
    return name.startswith(("test_", "tests"))


def _is_query_params_access(node: ast.expr) -> bool:
    """Detect query_params or GET access patterns.

    Matches:
        - .query_params.get() or .GET.get() calls
        - .query_params["key"] or .GET["key"] subscript access

    Args:
        node: The AST node to inspect.

    Returns:
        True when the node accesses query_params or GET.
    """
    if isinstance(node, ast.Call):
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"  # noqa: STRING_LITERAL
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr in ("query_params", "GET")
        ):
            return True
    if isinstance(node, ast.Subscript):
        if isinstance(node.value, ast.Attribute) and node.value.attr in ("query_params", "GET"):
            return True
    return False


def _has_suppression(line: str) -> bool:
    """Return whether a line suppresses the filterset check.

    Args:
        line: The source line to inspect.

    Returns:
        True when the suppression token is present.
    """
    return SUPPRESSION_TOKEN in line.lower()


class FiltersetVisitor(ast.NodeVisitor):
    """Visitor that flags direct query_params/GET access inside view classes."""

    def __init__(self, path: Path, lines: list[str]) -> None:
        super().__init__()
        self.path = path
        self.lines = lines
        self.errors: list[tuple[int, int]] = []
        self._in_view_class = False

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        saved = self._in_view_class
        if _is_view_class(node):
            self._in_view_class = True
        self.generic_visit(node)
        self._in_view_class = saved

    def _check_node(self, node: ast.expr) -> None:
        if not self._in_view_class:
            return
        if not _is_query_params_access(node):
            return
        line_index = max(node.lineno - 1, 0)
        if line_index < len(self.lines) and _has_suppression(self.lines[line_index]):
            return
        self.errors.append((node.lineno, node.col_offset))

    def visit_Call(self, node: ast.Call) -> None:
        self._check_node(node)
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        self._check_node(node)
        self.generic_visit(node)


def check_file(path: Path) -> list[tuple[int, int]]:
    """Return errors for direct query_params/GET access in view classes.

    Args:
        path: Path to the file to inspect.

    Returns:
        A list of (line, column) error locations.
    """
    if _should_skip_file(path):
        return []

    try:
        contents = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"{path}:0:0: USE_FILTERSET could not read file: {exc}")
        return [(0, 0)]

    try:
        tree = ast.parse(contents, filename=str(path))
    except SyntaxError as exc:
        lineno = exc.lineno or 0
        offset = exc.offset or 0
        print(f"{path}:{lineno}:{offset}: USE_FILTERSET syntax error: {exc.msg}")
        return [(lineno, offset)]

    lines = contents.splitlines()
    visitor = FiltersetVisitor(path, lines)
    visitor.visit(tree)
    return visitor.errors


def main(argv: list[str]) -> int:
    """Run the filterset enforcement check.

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
                f"{path}:{line}:{column}: USE_FILTERSET "
                "Use a FilterSet class instead of accessing query_params/GET directly. "
                "Add # noqa: USE_FILTERSET to suppress."
            )
    return 1 if errors_found else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
