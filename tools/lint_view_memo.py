"""Reject per-request state kept on views and serializers (#3597, ADR-0260).

Two spellings of one mistake:

1. ``_thing: T | None = None`` at class level, filled lazily during a request so
   later methods reuse it: a per-request memo hiding as a class attribute.
2. ``if not hasattr(self, "_thing"): self._thing = ...`` inside a method, which
   is the same memo without even a declaration to notice.

Both are thread-safe only because DRF builds a fresh view/serializer per request,
their state is invisible in every signature, reordering two method calls silently
changes the query count, and the first spelling's class-level default looks shared.
An attribute that outlives the request (a memo on an idmapper-cached model, say)
is worse still: it serves one request's answer to every later one.

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

# A class is a view or serializer when its own name, or one of its bases, ends in
# one of these. Test classes (``...Tests``, ``APITestCase``) deliberately do not.
VIEW_SUFFIXES = ("Serializer", "ViewSet", "View", "APIView")


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


def _base_name(base: ast.expr) -> str:
    """The trailing identifier of a base class expression (``a.b.Cls`` -> ``Cls``)."""
    if isinstance(base, ast.Attribute):
        return base.attr
    if isinstance(base, ast.Name):
        return base.id
    return ""


def _is_view_or_serializer(node: ast.ClassDef) -> bool:
    """Whether ``node`` names a DRF view or serializer, by its own name or a base's."""
    names = [node.name, *(_base_name(base) for base in node.bases)]
    return any(name.endswith(VIEW_SUFFIXES) for name in names)


def _self_attribute_target(target: ast.expr) -> str | None:
    """Return the attribute name when ``target`` is ``self._name`` (not dunder)."""
    if not isinstance(target, ast.Attribute):
        return None
    if not isinstance(target.value, ast.Name) or target.value.id != "self":
        return None
    if not target.attr.startswith("_") or target.attr.startswith("__"):
        return None
    return target.attr


def _lazy_state(stmt: ast.stmt) -> list[tuple[int, int, str]]:
    """Return every ``self._name = ...`` write and ``hasattr(self, ...)`` read in a method."""
    hits: list[tuple[int, int, str]] = []
    for node in ast.walk(stmt):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            targets = [node.target]
        for target in targets:
            name = _self_attribute_target(target)
            if name is not None:
                hits.append((node.lineno, node.col_offset, name))
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"hasattr", "setattr"}
            and node.args
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == "self"
        ):
            hits.append((node.lineno, node.col_offset, f"{node.func.id}(self, ...)"))
    # ast.walk is breadth-first; report in source order so the output reads top-down.
    return sorted(hits)


class MemoVisitor(ast.NodeVisitor):
    """Collect every unsuppressed per-request memo in a view or serializer class."""

    def __init__(self, lines: list[str]) -> None:
        super().__init__()
        self.lines = lines
        self.errors: list[tuple[int, int, str]] = []

    def _record(self, hits: list[tuple[int, int, str]]) -> None:
        """Keep the hits whose own line carries no suppression comment."""
        for hit in hits:
            line_index = hit[0] - 1
            if line_index < len(self.lines) and has_suppression(self.lines[line_index]):
                continue
            self.errors.append(hit)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for stmt in node.body:
            hit = _private_none_default(stmt)
            if hit is not None:
                self._record([hit])
            # The lazy spelling is only checked on views and serializers, where DRF
            # guarantees the per-request instance that makes it look harmless. A
            # plain class assigning to self in a method is ordinary object state.
            if (
                _is_view_or_serializer(node)
                and isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))
                and stmt.name != "__init__"
            ):
                self._record(_lazy_state(stmt))
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
                f"{filename}:{lineno}:{col + 1}: `{name}` keeps per-request state on a view "
                "or serializer, the shape ADR-0260 rejects. Account data goes on the Account "
                "typeclass as a cached_property; request data is passed as an explicit "
                "argument (serializer `context=`, or `validated_data` for a row resolved "
                "during validation) or attached by middleware. Suppress with "
                "`# noqa: VIEW_MEMO` plus a reason only for constant configuration."
            )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
