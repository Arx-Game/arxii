"""Reject concrete Django models that inherit from models.Model instead of SharedMemoryModel.

Use "# noqa: SHARED_MEMORY" to suppress a specific instance.
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys

SUPPRESSION_TOKEN = "noqa: shared_memory"  # noqa: S105
_MODEL_BASES = {"models.Model", "Model"}


def _get_base_name(node: ast.expr) -> str | None:
    """Extract dotted name from an AST base class node.

    Args:
        node: An AST expression node representing a base class.

    Returns:
        The dotted name string, or None if the node is not a simple name.
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return f"{node.value.id}.{node.attr}"
    return None


def _is_abstract(class_node: ast.ClassDef) -> bool:
    """Check if a class has abstract = True in a nested Meta class.

    Args:
        class_node: The AST class definition node.

    Returns:
        True when the class declares abstract = True in its Meta.
    """
    for item in class_node.body:
        if isinstance(item, ast.ClassDef) and item.name == "Meta":  # noqa: STRING_LITERAL
            for meta_item in item.body:
                if (
                    isinstance(meta_item, ast.Assign)
                    and len(meta_item.targets) == 1
                    and isinstance(meta_item.targets[0], ast.Name)
                    and meta_item.targets[0].id == "abstract"  # noqa: STRING_LITERAL
                    and isinstance(meta_item.value, ast.Constant)
                    and meta_item.value.value is True
                ):
                    return True
    return False


def _should_skip_file(path: Path) -> bool:
    """Determine whether a file should be skipped entirely.

    Args:
        path: Path to the file.

    Returns:
        True when the file is in a migrations directory or is a test file.
    """
    if "migrations" in path.parts:  # noqa: STRING_LITERAL
        return True
    name = path.name
    if name.startswith(("test_", "tests")):
        return True
    return False


class SharedMemoryVisitor(ast.NodeVisitor):
    """Visitor that flags concrete model classes not using SharedMemoryModel."""

    def __init__(self, path: Path, lines: list[str]) -> None:
        super().__init__()
        self.path = path
        self.lines = lines
        self.errors: list[tuple[int, int, str]] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        base_names = [_get_base_name(b) for b in node.bases]
        if any(name in _MODEL_BASES for name in base_names):
            if not _is_abstract(node):
                line_index = max(node.lineno - 1, 0)
                if line_index < len(self.lines):
                    line_text = self.lines[line_index]
                    if SUPPRESSION_TOKEN in line_text.lower():
                        self.generic_visit(node)
                        return
                self.errors.append((node.lineno, node.col_offset, node.name))
        self.generic_visit(node)


def check_file(path: Path) -> list[tuple[int, int, str]]:
    """Return errors for concrete models not using SharedMemoryModel.

    Args:
        path: Path to the file to inspect.

    Returns:
        A list of (line, column, class_name) error tuples.
    """
    if _should_skip_file(path):
        return []

    try:
        contents = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"{path}:0:0: SHARED_MEMORY could not read file: {exc}")
        return [(0, 0, "")]

    try:
        tree = ast.parse(contents, filename=str(path))
    except SyntaxError as exc:
        lineno = exc.lineno or 0
        offset = exc.offset or 0
        print(f"{path}:{lineno}:{offset}: SHARED_MEMORY syntax error: {exc.msg}")
        return [(lineno, offset, "")]

    lines = contents.splitlines()
    visitor = SharedMemoryVisitor(path, lines)
    visitor.visit(tree)
    return visitor.errors


def main(argv: list[str]) -> int:
    """Run the SharedMemoryModel enforcement check.

    Args:
        argv: Command-line arguments (file paths).

    Returns:
        Exit status code.
    """
    errors_found = False
    for raw_path in argv:
        path = Path(raw_path)
        if path.suffix != ".py":
            continue
        errors = check_file(path)
        for line, col, class_name in errors:
            errors_found = True
            column = col + 1 if col else 0
            print(
                f"{path}:{line}:{column}: SHARED_MEMORY "
                f"class {class_name} should use SharedMemoryModel "
                f"instead of models.Model. "
                f"Add # noqa: SHARED_MEMORY with justification to suppress."
            )
    return 1 if errors_found else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
