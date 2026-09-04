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

Use `# noqa: OBJECTDB_PARAM` on the same line as the annotation to suppress
when ObjectDB is genuinely the right type.

It ALSO flags model relation fields that point at ObjectDB (#2608) —
`ForeignKey`/`OneToOneField`/`ManyToManyField` whose target resolves to
`objects.ObjectDB`. Same reasoning one layer down: an FK to ObjectDB accepts a
vase where a character or room was meant. Suppress a deliberate keeper with
`# noqa: OBJECTDB_FIELD`, either inside the field's own statement or in the
comment block directly above it (the rationale comment the audit already
writes — see CLAUDE.md's "Avoid direct FKs to ObjectDB").

Module-level aliases are resolved, so the `_OBJECTDB_MODEL = "objects.ObjectDB"`
indirection several apps use to dedupe the string cannot hide a field.
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys

SUPPRESSION_TOKEN = "noqa: objectdb_param"  # noqa: S105
FIELD_SUPPRESSION_TOKEN = "noqa: objectdb_field"  # noqa: S105

# Relation fields whose first positional argument names the target model.
_RELATION_FIELDS = frozenset({"ForeignKey", "OneToOneField", "ManyToManyField"})

# The dotted model path Django resolves to Evennia's ObjectDB.
_OBJECTDB_MODEL_PATHS = frozenset({"objects.ObjectDB", "ObjectDB"})
_OBJECTDB_MODEL_PATHS_LOWER = frozenset(p.lower() for p in _OBJECTDB_MODEL_PATHS)

# Names that count as "ObjectDB" annotations. Includes the bare name and the
# typical attribute-access form. Substring match on the last component handles
# `evennia.objects.models.ObjectDB`, `models.ObjectDB`, etc.
_OBJECTDB_NAME = "ObjectDB"


def _annotation_is_objectdb(node: ast.expr | None) -> bool:
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


def _collect_objectdb_aliases(tree: ast.Module) -> set[str]:
    """Return module-level names bound to the ObjectDB model path.

    Several apps dedupe the repeated string via a module constant
    (`_OBJECTDB_MODEL = "objects.ObjectDB"`). Without resolving those, every
    field written as `models.ForeignKey(_OBJECTDB_MODEL, ...)` would slip past
    the check — which is most of them in `dreams`, `missions` and `combat`.
    """
    aliases: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        value = node.value
        if not (isinstance(value, ast.Constant) and isinstance(value.value, str)):
            continue
        if value.value.lower() not in _OBJECTDB_MODEL_PATHS_LOWER:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                aliases.add(target.id)
    return aliases


def _field_target_is_objectdb(node: ast.expr | None, aliases: set[str]) -> bool:
    """Return whether a relation field's target argument resolves to ObjectDB.

    Model reference strings are matched case-insensitively — Django resolves
    ``"objects.objectdb"`` and ``"objects.ObjectDB"`` to the same model, and the
    lowercase form is what its own generated migrations write.
    """
    if node is None:
        return False
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.lower() in _OBJECTDB_MODEL_PATHS_LOWER
    if isinstance(node, ast.Name):
        return node.id == _OBJECTDB_NAME or node.id in aliases
    if isinstance(node, ast.Attribute):
        return node.attr == _OBJECTDB_NAME
    return False


def _relation_target_arg(node: ast.Call) -> ast.expr | None:
    """Return the node naming a relation field's target model.

    Django accepts the target positionally *or* as the ``to=`` keyword; both
    forms have to be checked, or a field written as
    ``ForeignKey(to="objects.ObjectDB")`` slips past the ratchet silently.
    """
    if node.args:
        return node.args[0]
    for kw in node.keywords:
        if kw.arg == "to":
            return kw.value
    return None


def _field_call_name(func: ast.expr) -> str | None:
    """Return the relation-field name for a call (`models.ForeignKey` -> ForeignKey)."""
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


class ObjectDBFieldVisitor(ast.NodeVisitor):
    """Visitor that flags model relation fields targeting ObjectDB (#2608)."""

    def __init__(self, lines: list[str], aliases: set[str]) -> None:
        super().__init__()
        self.lines = lines
        self.aliases = aliases
        self.errors: list[tuple[int, int, str]] = []

    def _suppressed(self, node: ast.Call) -> bool:
        """Whether the field's own lines, or the comments above it, opt out.

        The audit's convention is a prose rationale comment directly above the
        field, so the token is accepted there as well as inside the call.
        """
        start = node.lineno - 1
        end = node.end_lineno or node.lineno
        for line in self.lines[start:end]:
            if FIELD_SUPPRESSION_TOKEN in line.lower():
                return True
        # Walk the contiguous comment block immediately above the statement.
        index = start - 1
        while index >= 0 and self.lines[index].lstrip().startswith("#"):
            if FIELD_SUPPRESSION_TOKEN in self.lines[index].lower():
                return True
            index -= 1
        return False

    def visit_Call(self, node: ast.Call) -> None:
        name = _field_call_name(node.func)
        if name in _RELATION_FIELDS:
            target = _relation_target_arg(node)
            if _field_target_is_objectdb(target, self.aliases) and not self._suppressed(node):
                self.errors.append((node.lineno, node.col_offset, f"{name} target"))
        self.generic_visit(node)


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
        assert annotation is not None  # noqa: S101
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


def check_file(path: Path) -> list[tuple[int, int, str, str]]:
    """Return errors for ObjectDB-typed signatures and model fields in one file.

    Each entry is ``(line, column, label, kind)`` where ``kind`` is ``"param"``
    (a service signature) or ``"field"`` (a model relation field).
    """
    if _should_skip_file(path):
        return []
    try:
        contents = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"{path}:0:0: OBJECTDB_PARAM could not read file: {exc}")
        return [(0, 0, "read error", "param")]
    try:
        tree = ast.parse(contents, filename=str(path))
    except SyntaxError as exc:
        lineno = exc.lineno or 0
        offset = exc.offset or 0
        print(f"{path}:{lineno}:{offset}: OBJECTDB_PARAM syntax error: {exc.msg}")
        return [(lineno, offset, "syntax error", "param")]
    lines = contents.splitlines()
    visitor = ObjectDBVisitor(lines)
    visitor.visit(tree)
    results: list[tuple[int, int, str, str]] = [
        (line, col, label, "param") for line, col, label in visitor.errors
    ]

    field_visitor = ObjectDBFieldVisitor(lines, _collect_objectdb_aliases(tree))
    field_visitor.visit(tree)
    results.extend((line, col, label, "field") for line, col, label in field_visitor.errors)
    results.sort()
    return results


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
        for line, col, label, kind in check_file(path):
            errors_found = True
            column = col + 1 if col else 0
            if kind == "field":
                print(
                    f"{path}:{line}:{column}: OBJECTDB_FIELD "
                    f"Model {label} points at ObjectDB; point it at the specific model "
                    "(CharacterSheet, RoomProfile, Persona, RosterEntry, etc.) or add "
                    "`# noqa: OBJECTDB_FIELD` — in the field or the comment above it — "
                    "stating why any game object is genuinely right. See #2608."
                )
            else:
                print(
                    f"{path}:{line}:{column}: OBJECTDB_PARAM "
                    f"Service-layer {label} typed as ObjectDB; use the narrower model "
                    "(CharacterSheet, Persona, RosterEntry, RoomProfile, etc.) or add "
                    "`# noqa: OBJECTDB_PARAM` if ObjectDB is "
                    "genuinely the right type."
                )
    return 1 if errors_found else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
