"""Reject mutate-then-save-then-raise inside an atomic block (Apostate ruling 7, 2026-08-27).

Evennia's idmapper (`evennia.utils.idmapper.models.SharedMemoryModel`) returns the
same cached in-memory instance for a given pk from every `.get()`/`.filter()` call
that hits it — that is the entire point of the identity-map cache (see ADR-0008). If
code inside `transaction.atomic()` mutates a cached instance's attribute in place
(`obj.balance -= amount`) and calls `obj.save()`, and *then* raises — closing the
block and rolling back the database write — the row in Postgres reverts but the
mutated Python object sitting in the identity map does not: nothing about a rollback
touches process memory, and Evennia disables the `request_finished` flush that would
otherwise clear it between requests. The phantom value survives for the process
lifetime; the next read for that pk hands back the poisoned instance.

The fix is always an ordering fix: finish all validation/raises before the first
in-place mutation. This linter is deliberately narrow — it does not try to flag every
possible mutate-then-raise shape (too noisy for real service code, which mixes
mutation with plenty of unrelated branching). It flags exactly the shape that bit us:
within a `with transaction.atomic():` block (or a function decorated
`@transaction.atomic`), a `raise` statement that textually follows both an
augmented/attribute assignment on some name (`obj.field -= x` or `obj.field = x`) and
a `.save(...)` call on that same name, anywhere earlier in the same atomic scope
(including inside a preceding sibling `if`/`try`/`with`/`for`/`while` branch whose
state carries forward). See `django_notes.md`'s "Idmapper Rollback Staleness" section
and ADR-0008's addendum for the full writeup, and the test-side
`flush_instance_cache()` convention for tests that intentionally trigger a rollback.

Use `# noqa: IDMAPPER_MUTATE_ORDER` on the `raise` line to suppress, with a reason —
e.g. when the raise is provably outside the transaction's rollback path, or the
mutated instance is deliberately re-fetched/flushed before any further read.
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys

SUPPRESSION_TOKEN = "noqa: idmapper_mutate_order"  # noqa: S105

# Compound-statement kinds whose nested bodies execute as part of the same
# sequential flow as their enclosing block. We recurse into these (forking a
# copy of the accumulated mutate/save state per branch); we do NOT recurse into
# FunctionDef/AsyncFunctionDef/ClassDef bodies, which are separate scopes handled
# by their own top-level visit.
_ATOMIC_CALL_NAME = "atomic"


def _is_atomic_attr(node: ast.expr) -> bool:
    """True for `transaction.atomic` (attribute) or a bare `atomic` name (direct import)."""
    if isinstance(node, ast.Attribute):
        return node.attr == _ATOMIC_CALL_NAME
    if isinstance(node, ast.Name):
        return node.id == _ATOMIC_CALL_NAME
    return False


def _is_atomic_expr(node: ast.expr | None) -> bool:
    """True for `transaction.atomic` or `transaction.atomic(...)`, bare or called."""
    if node is None:
        return False
    if isinstance(node, ast.Call):
        return _is_atomic_attr(node.func)
    return _is_atomic_attr(node)


def _mutated_name(stmt: ast.stmt) -> str | None:
    """Return the name whose attribute `stmt` mutates in place, if any.

    Covers `obj.field = value` (Assign) and `obj.field += value` (AugAssign) where
    the mutated object is a bare local name. A reassignment of the name itself
    (`obj = value`) is not a mutation of the cached instance and is not flagged.
    """
    if isinstance(stmt, ast.Assign):
        for target in stmt.targets:
            if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                return target.value.id
        return None
    if isinstance(stmt, ast.AugAssign):
        target = stmt.target
        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
            return target.value.id
        return None
    return None


def _saved_name(stmt: ast.stmt) -> str | None:
    """Return the name a bare `obj.save(...)` expression statement is called on, if any."""
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
        func = stmt.value.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "save"
            and isinstance(func.value, ast.Name)
        ):
            return func.value.id
    return None


def _sub_bodies(stmt: ast.stmt) -> list[list[ast.stmt]]:
    """Return the nested statement lists that execute as part of `stmt`'s own flow."""
    bodies: list[list[ast.stmt]] = []
    if isinstance(stmt, ast.If):
        bodies.extend((stmt.body, stmt.orelse))
    elif isinstance(stmt, ast.Try):
        bodies.append(stmt.body)
        bodies.extend(handler.body for handler in stmt.handlers)
        bodies.extend((stmt.orelse, stmt.finalbody))
    elif isinstance(stmt, ast.With | ast.AsyncWith):
        bodies.append(stmt.body)
    elif isinstance(stmt, ast.For | ast.AsyncFor | ast.While):
        bodies.extend((stmt.body, stmt.orelse))
    return [body for body in bodies if body]


class IdmapperMutationOrderVisitor(ast.NodeVisitor):
    """Visitor that flags mutate-then-save-then-raise inside atomic scopes."""

    def __init__(self, lines: list[str]) -> None:
        super().__init__()
        self.lines = lines
        self.errors: list[tuple[int, int, str]] = []

    def visit_With(self, node: ast.With) -> None:
        if any(_is_atomic_expr(item.context_expr) for item in node.items):
            self._walk(node.body, set(), set())
        self.generic_visit(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        if any(_is_atomic_expr(item.context_expr) for item in node.items):
            self._walk(node.body, set(), set())
        self.generic_visit(node)

    def _check_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if any(_is_atomic_expr(decorator) for decorator in node.decorator_list):
            self._walk(node.body, set(), set())

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_function(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_function(node)
        self.generic_visit(node)

    def _walk(self, stmts: list[ast.stmt], mutated: set[str], saved: set[str]) -> None:
        for stmt in stmts:
            name = _mutated_name(stmt)
            if name is not None:
                mutated.add(name)
                continue
            name = _saved_name(stmt)
            if name is not None:
                saved.add(name)
                continue
            if isinstance(stmt, ast.Raise):
                poisoned = mutated & saved
                if poisoned and not self._suppressed(stmt):
                    label = ", ".join(sorted(poisoned))
                    self.errors.append((stmt.lineno, stmt.col_offset, label))
                continue
            for sub_body in _sub_bodies(stmt):
                self._walk(sub_body, set(mutated), set(saved))

    def _suppressed(self, node: ast.stmt) -> bool:
        line_index = node.lineno - 1
        if 0 <= line_index < len(self.lines):
            return SUPPRESSION_TOKEN in self.lines[line_index].lower()
        return False


def check_file(path: Path) -> list[tuple[int, int, str]]:
    """Return `(line, column, name)` for each mutate-save-then-raise violation."""
    try:
        contents = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"{path}:0:0: IDMAPPER_MUTATE_ORDER could not read file: {exc}")
        return [(0, 0, "read error")]
    try:
        tree = ast.parse(contents, filename=str(path))
    except SyntaxError as exc:
        lineno = exc.lineno or 0
        offset = exc.offset or 0
        print(f"{path}:{lineno}:{offset}: IDMAPPER_MUTATE_ORDER syntax error: {exc.msg}")
        return [(lineno, offset, "syntax error")]

    lines = contents.splitlines()
    visitor = IdmapperMutationOrderVisitor(lines)
    visitor.visit(tree)

    # Dedupe: a nested atomic block is walked once from its own enclosing scope
    # AND again when the visitor's own traversal reaches it directly.
    seen: set[tuple[int, int]] = set()
    results: list[tuple[int, int, str]] = []
    for line, col, label in sorted(visitor.errors):
        key = (line, col)
        if key in seen:
            continue
        seen.add(key)
        results.append((line, col, label))
    return results


def main(argv: list[str]) -> int:
    """Run the idmapper-mutate-order check across the given file paths.

    Pre-commit invokes this with the staged files under the hook's `files:` scope
    (`.pre-commit-config.yaml`).
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
                f"{path}:{line}:{column}: IDMAPPER_MUTATE_ORDER "
                f"raise after mutate-then-save on {label!r} inside an atomic block leaves "
                "the identity-map cache poisoned on rollback (the DB row reverts; the "
                "cached instance doesn't - see ADR-0008's addendum). Move all "
                "validation/raises before the first in-place mutation, or add "
                "`# noqa: IDMAPPER_MUTATE_ORDER` stating why this ordering is safe here."
            )
    return 1 if errors_found else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
