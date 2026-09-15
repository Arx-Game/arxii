"""Reject a persisted Interaction row that nobody ever delivers live (#3807).

Before this issue, three production writers built an ``Interaction`` row, wrote its
target rows, saved the row's foreign key back onto a request, and returned -- with no
WebSocket push and no telnet line to anybody, ever: ``_create_result_interaction`` and
``_resolve_treatment_request`` (``world/scenes/action_services.py``) and
``create_cast_outcome_pose`` (``world/scenes/cast_services.py``). Every other
production ``create_interaction`` caller in the codebase delivers its row through a
push seam in the same breath. Nothing caught it: the tests asserted the row existed in
the database, a REST refetch or a scene-log reread made the row look fine, and there
was no lint for "you built this, now tell somebody." The row sat there, correct and
inert, and a player who took a social action never saw what it did -- the thing the
issue was filed to question ("should we show this at all?") when the real defect was
narrower: showing it was never optional, only *who sees it* was ever a design
question.

The rule: every call to ``create_interaction`` (bare name or ``x.create_interaction``)
must be matched, in its own function or an enclosing function, by a call to one of the
delivery seams: ``push_interaction``, ``deliver_outcome_interaction``,
``push_ephemeral_interaction``, ``_send_to_objects``, ``_broadcast_to_location``. A
nested closure defined inside the writing function counts as "its own function" for a
call made inside that closure; a delivery call sitting in an ancestor function also
covers a ``create_interaction`` call made in a descendant closure. This is a purely
structural check -- it does not trace which branch actually runs, only that a seam call
exists somewhere in the right lexical scope. A call at module level, with no enclosing
function to carry a seam, is always a finding.

Use ``# noqa: UNDELIVERED`` on the call's own line (or the line its opening paren sits
on) to suppress, with a reason. The only legitimate reason found in this codebase: the
function returns the created row to a caller that delivers it itself (e.g.
``audere_majora._post_declaration`` hands its row back to ``cross_threshold``, which
pushes it) -- never "delivery happens somewhere else I didn't check."
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys

SUPPRESSION_TOKEN = "noqa: undelivered"  # noqa: S105

CREATE_NAME = "create_interaction"

DELIVERY_SEAMS = frozenset(
    {
        "push_interaction",
        "deliver_outcome_interaction",
        "push_ephemeral_interaction",
        "_send_to_objects",
        "_broadcast_to_location",
    }
)


def has_suppression(line: str) -> bool:
    """Return whether ``line`` carries the suppression token."""
    return SUPPRESSION_TOKEN in line.lower()


def _call_target_name(node: ast.Call) -> str | None:
    """The bare or attribute name a call targets (``f(...)`` or ``x.f(...)``)."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


class _Scope:
    """One function's (or the module's) own lexical scope."""

    def __init__(self, parent: _Scope | None) -> None:
        self.parent = parent
        self.creates: list[ast.Call] = []
        self.has_delivery = False

    def is_covered(self) -> bool:
        """Whether this scope or any enclosing scope carries a delivery-seam call."""
        scope: _Scope | None = self
        while scope is not None:
            if scope.has_delivery:
                return True
            scope = scope.parent
        return False


class _Visitor(ast.NodeVisitor):
    """Walk the module, tracking lexical function scope for each Call node.

    Every scope created (module + each non-``create_interaction`` function/closure) is
    kept in ``self.scopes`` so the caller can check coverage across the whole tree
    after the walk completes.
    """

    def __init__(self) -> None:
        super().__init__()
        module_scope = _Scope(parent=None)
        self.scopes: list[_Scope] = [module_scope]
        self._stack: list[_Scope] = [module_scope]

    def _current(self) -> _Scope:
        return self._stack[-1]

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_target_name(node)
        scope = self._current()
        if name == CREATE_NAME:
            scope.creates.append(node)
        elif name in DELIVERY_SEAMS:
            scope.has_delivery = True
        self.generic_visit(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if node.name == CREATE_NAME:
            # Skip create_interaction's own definition entirely -- not a call site.
            return
        scope = _Scope(parent=self._current())
        self.scopes.append(scope)
        self._stack.append(scope)
        self.generic_visit(node)
        self._stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)


def check_source(source: str) -> list[tuple[int, int, str]]:
    """Return ``(line, col, name)`` for every undelivered ``create_interaction`` call."""
    tree = ast.parse(source)
    visitor = _Visitor()
    visitor.visit(tree)

    lines = source.splitlines()
    errors: list[tuple[int, int, str]] = []
    for scope in visitor.scopes:
        if scope.is_covered():
            continue
        for call in scope.creates:
            line_index = call.lineno - 1
            if line_index < len(lines) and has_suppression(lines[line_index]):
                continue
            errors.append((call.lineno, call.col_offset, CREATE_NAME))
    return sorted(errors)


def check_file(path: Path) -> list[tuple[int, int, str]]:
    """Return the undelivered-interaction errors in the file at ``path``."""
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
                f"{filename}:{lineno}:{col + 1}: `{name}` persists a row nobody delivers "
                "live (#3807) -- no WebSocket push, no telnet line, to anybody, ever. Pair "
                "it with a delivery seam (`push_interaction`, `deliver_outcome_interaction`, "
                "`push_ephemeral_interaction`, `_send_to_objects`, or `_broadcast_to_location`) "
                "in the same function or an enclosing one. Suppress with `# noqa: UNDELIVERED` "
                "plus a reason only when this function returns the row to a caller that "
                "delivers it."
            )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
