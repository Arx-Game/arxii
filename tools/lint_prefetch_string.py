"""Reject prefetch_related() calls with bare string arguments.

Always use Prefetch() objects with to_attr for explicit, cache-safe prefetching.
Bare strings cause stale data issues with SharedMemoryModel and return
querysets instead of lists.

Use "# noqa: PREFETCH_STRING" to suppress a specific instance.
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys

SUPPRESSION_TOKEN = "noqa: prefetch_string"  # noqa: S105


def has_suppression(line: str) -> bool:
    """Return whether a line suppresses the prefetch string check.

    Args:
        line: The source line to inspect.

    Returns:
        True when the suppression token is present.
    """
    return SUPPRESSION_TOKEN in line.lower()


def is_prefetch_related_call(node: ast.Call) -> bool:
    """Return whether a call node is a prefetch_related invocation.

    Args:
        node: The AST call node.

    Returns:
        True when the call targets prefetch_related.
    """
    if isinstance(node.func, ast.Attribute) and node.func.attr == "prefetch_related":
        return True
    return False


def find_bare_string_args(node: ast.Call) -> list[ast.Constant]:
    """Return any bare string arguments in a prefetch_related call.

    Args:
        node: The AST call node.

    Returns:
        List of string constant nodes that should be Prefetch objects.
    """
    bare_strings = []
    for arg in node.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            bare_strings.append(arg)
    return bare_strings


class PrefetchStringVisitor(ast.NodeVisitor):
    """Visitor that collects prefetch_related calls with bare string arguments."""

    def __init__(self, path: Path, lines: list[str]) -> None:
        super().__init__()
        self.path = path
        self.lines = lines
        self.errors: list[tuple[int, int, str]] = []

    def visit_Call(self, node: ast.Call) -> None:
        if is_prefetch_related_call(node):
            for string_arg in find_bare_string_args(node):
                line_index = max(string_arg.lineno - 1, 0)
                if line_index < len(self.lines) and has_suppression(self.lines[line_index]):
                    continue
                self.errors.append((string_arg.lineno, string_arg.col_offset, string_arg.value))
        self.generic_visit(node)


def check_file(path: Path) -> list[tuple[int, int, str]]:
    """Return errors for bare string prefetch_related args in a file.

    Args:
        path: Path to the file to inspect.

    Returns:
        A list of (line, column, value) error locations.
    """
    try:
        contents = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"{path}:0:0: PREFETCH_STRING could not read file: {exc}")
        return [(0, 0, "")]

    try:
        tree = ast.parse(contents, filename=str(path))
    except SyntaxError as exc:
        lineno = exc.lineno or 0
        offset = exc.offset or 0
        print(f"{path}:{lineno}:{offset}: PREFETCH_STRING syntax error: {exc.msg}")
        return [(lineno, offset, "")]

    lines = contents.splitlines()
    visitor = PrefetchStringVisitor(path, lines)
    visitor.visit(tree)
    return visitor.errors


def main(argv: list[str]) -> int:
    """Run the prefetch string check.

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
        for line, col, value in errors:
            errors_found = True
            column = col + 1 if col else 0
            print(
                f"{path}:{line}:{column}: PREFETCH_STRING "
                f'Use Prefetch("{value}", queryset=..., to_attr="...") '
                f"instead of bare string. Add # noqa: PREFETCH_STRING to suppress."
            )
    return 1 if errors_found else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
