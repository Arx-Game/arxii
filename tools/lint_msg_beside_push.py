"""Reject an untargeted ``.msg(text)`` in a function that also pushes a structured row (#4418).

``character.msg(text)`` with no ``session=`` reaches every session the character has,
the browser included. A function that pushes an interaction row to the web
(``push_interaction``, ``deliver_outcome_interaction``, ``push_ephemeral_interaction``,
``_send_to_objects``, ``_broadcast_to_location``) and then also calls a bare ``.msg(...)``
shows the line twice on ``/game``: once as the row and once as a plain "note".
``deliver_aftermath_digests``, ``narrate_privately``, ``narrate_companion_loss`` and
``_narrate_gm_condition`` all did this (real-testing bug K).

The text twin belongs on the telnet sessions only: use
``world.scenes.interaction_services.send_text_to_non_web(obj, text)``, or pass
``session=non_web_sessions(obj)``. A ``.msg`` that passes any ``session=`` keyword is fine.

The check is structural and per function: any ``.msg(...)`` call without a ``session``
keyword in a function (nested closures count toward their enclosing function) that also
calls one of the seams above. ``# noqa: MSG_BESIDE_PUSH`` on the call line suppresses it
and must say why (typically: this branch pushes no row, so the text is the only copy).
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys

SUPPRESSION_TOKEN = "noqa: msg_beside_push"  # noqa: S105
_SEAMS = frozenset(
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


def _call_name(node: ast.Call) -> str | None:
    """Return the bare or attribute name a call invokes."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def check_source(source: str) -> list[tuple[int, int]]:
    """Return ``(lineno, col)`` for every untargeted ``.msg`` beside a structured push."""
    tree = ast.parse(source)
    lines = source.splitlines()
    hits: set[tuple[int, int]] = set()
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)]
        if not any(_call_name(c) in _SEAMS for c in calls):
            continue
        for call in calls:
            if not (isinstance(call.func, ast.Attribute) and call.func.attr == "msg"):
                continue
            if any(k.arg == "session" for k in call.keywords):
                continue
            span = range(call.lineno, (call.end_lineno or call.lineno) + 1)
            if any(has_suppression(lines[n - 1]) for n in span if 0 < n <= len(lines)):
                continue
            hits.add((call.lineno, call.col_offset))
    return sorted(hits)


def check_file(path: Path) -> list[tuple[int, int]]:
    """Return the offending calls in the file at ``path``."""
    try:
        return check_source(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return []


def main(argv: list[str]) -> int:
    """Lint the given files; print each violation and return 1 if any were found."""
    failed = False
    for filename in argv:
        for lineno, col in check_file(Path(filename)):
            failed = True
            print(
                f"{filename}:{lineno}:{col + 1}: untargeted `.msg(...)` in a function that "
                "also pushes a structured row. It reaches every session, so a browser gets "
                "the line twice (the row and a plain note) (#4418). Use "
                "`send_text_to_non_web(obj, text)` from `world.scenes.interaction_services`. "
                "Suppress with `# noqa: MSG_BESIDE_PUSH` plus a reason."
            )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
