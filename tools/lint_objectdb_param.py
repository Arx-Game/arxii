"""Reject ObjectDB-typed parameters/returns in service-layer functions.

`evennia.objects.models.ObjectDB` is Evennia's generic base for every game
object — characters, rooms, exits, items. A service function that accepts
`character: ObjectDB` and then walks `character.sheet_data.…` silently
admits "a vase of flowers" where a played character was meant. The narrower
model (`CharacterSheet`, `Persona`, `RosterEntry`, `RoomProfile`, etc.) is
self-documenting and prevents an entire class of mis-targeting bugs.

This linter flags `: ObjectDB` annotations on function arguments and return
types. Pre-commit's `files:` filter scopes it to service modules; flows,
object_states, commands, permissions, and Evennia internals genuinely
operate on any object and are out of scope by virtue of not being matched.

Use `# noqa: OBJECTDB_PARAM — <justification>` on the same line as the
annotation to suppress when ObjectDB is genuinely the right type. The
justification is required per CLAUDE.md's noqa-suppression policy.
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys

SUPPRESSION_TOKEN = "noqa: objectdb_param"  # noqa: S105

# Names that count as "ObjectDB" annotations. Includes the bare name and the
# typical attribute-access form. Substring match on the last component handles
# `evennia.objects.models.ObjectDB`, `models.ObjectDB`, etc.
_OBJECTDB_NAME = "ObjectDB"


def _annotation_is_objectdb(node: ast.expr | None) -> bool:  # noqa: PLR0911 — distinct AST cases, splitting would obscure the dispatch
    """Return True if the annotation refers to ObjectDB.

    Handles:
        - `ObjectDB`                              (Name)
        - `"ObjectDB"` (forward reference string) (Constant)
        - `models.ObjectDB`, `objects.ObjectDB`, `evennia.objects.models.ObjectDB`
          and any dotted-attribute chain ending in `ObjectDB`  (Attribute)
        - `ObjectDB | None`, `Optional[ObjectDB]`, `list[ObjectDB]` and other
          generic wrappers — recurses into BinOp / Subscript / Tuple.
    """
    if node is None:
        return False
    if isinstance(node, ast.Name):
        return node.id == _OBJECTDB_NAME
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        # Forward reference like `: "ObjectDB"` or `: "ObjectDB | None"`.
        return _OBJECTDB_NAME in node.value.split()
    if isinstance(node, ast.Attribute):
        return node.attr == _OBJECTDB_NAME
    if isinstance(node, ast.BinOp):
        # `X | Y` union — recurse into both sides.
        return _annotation_is_objectdb(node.left) or _annotation_is_objectdb(node.right)
    if isinstance(node, ast.Subscript):
        # `Optional[ObjectDB]`, `list[ObjectDB]`, etc. — recurse into the slice.
        return _annotation_is_objectdb(node.slice)
    if isinstance(node, ast.Tuple):
        return any(_annotation_is_objectdb(elt) for elt in node.elts)
    return False


def _has_suppression(line: str) -> bool:
    """Return whether a line suppresses the ObjectDB-param check."""
    return SUPPRESSION_TOKEN in line.lower()


class ObjectDBVisitor(ast.NodeVisitor):
    """Visitor that flags ObjectDB-typed args / returns in function signatures."""

    def __init__(self, lines: list[str]) -> None:
        super().__init__()
        self.lines = lines
        self.errors: list[tuple[int, int, str]] = []

    def _check_annotation(
        self, annotation: ast.expr | None, label: str, default_lineno: int
    ) -> None:
        if not _annotation_is_objectdb(annotation):
            return
        # AST annotation nodes always carry lineno + col_offset; default_lineno
        # is kept as a defensive fallback parameter but unused in practice.
        del default_lineno  # quiets unused-arg
        # _annotation_is_objectdb returns False for None, so annotation is not None here.
        assert annotation is not None  # noqa: S101 — narrowing for type checker; logically guaranteed by the early return above
        lineno = annotation.lineno
        line_index = max(lineno - 1, 0)
        if line_index < len(self.lines) and _has_suppression(self.lines[line_index]):
            return
        self.errors.append((lineno, annotation.col_offset, label))

    def _check_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        def_lineno = node.lineno
        # All argument categories: posonly, args, kwonly, vararg, kwarg
        all_args = list(node.args.posonlyargs) + list(node.args.args) + list(node.args.kwonlyargs)
        if node.args.vararg is not None:
            all_args.append(node.args.vararg)
        if node.args.kwarg is not None:
            all_args.append(node.args.kwarg)
        for arg in all_args:
            self._check_annotation(arg.annotation, f"argument {arg.arg!r}", def_lineno)
        self._check_annotation(node.returns, "return type", def_lineno)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_function(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_function(node)
        self.generic_visit(node)


def _should_skip_file(path: Path) -> bool:
    """Skip test files — they're allowed to construct fake characters as ObjectDB."""
    name = path.name
    return name.startswith(("test_", "tests"))


def check_file(path: Path) -> list[tuple[int, int, str]]:
    """Return errors for ObjectDB-typed signatures in a single file."""
    if _should_skip_file(path):
        return []
    try:
        contents = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"{path}:0:0: OBJECTDB_PARAM could not read file: {exc}")
        return [(0, 0, "read error")]
    try:
        tree = ast.parse(contents, filename=str(path))
    except SyntaxError as exc:
        lineno = exc.lineno or 0
        offset = exc.offset or 0
        print(f"{path}:{lineno}:{offset}: OBJECTDB_PARAM syntax error: {exc.msg}")
        return [(lineno, offset, "syntax error")]
    lines = contents.splitlines()
    visitor = ObjectDBVisitor(lines)
    visitor.visit(tree)
    return visitor.errors


def main(argv: list[str]) -> int:
    """Run the ObjectDB-param check across the given file paths.

    Pre-commit invokes this with the staged service files (scoped via the
    `files:` filter in `.pre-commit-config.yaml`).
    """
    errors_found = False
    for raw_path in argv:
        path = Path(raw_path)
        if path.suffix != ".py":
            continue
        for line, col, label in check_file(path):
            errors_found = True
            column = col + 1 if col else 0
            print(
                f"{path}:{line}:{column}: OBJECTDB_PARAM "
                f"Service-layer {label} typed as ObjectDB; use the narrower model "
                "(CharacterSheet, Persona, RosterEntry, RoomProfile, etc.) or add "
                "`# noqa: OBJECTDB_PARAM — <justification>` if ObjectDB is "
                "genuinely the right type."
            )
    return 1 if errors_found else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
