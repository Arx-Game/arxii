"""Reject ``.msg(type=...)`` and ``.msg(kwargs=...)`` (#4774).

Evennia turns every keyword given to ``msg`` into its own output command named after
the keyword. ``session.msg(type="action_result", kwargs={...})`` therefore reaches the
browser as two frames, ``["type", ["action_result"], {}]`` and ``["kwargs", [], {...}]``,
and the client, which dispatches on the frame name, handles neither. ``execute_action``
sent every web action's reply this way for six months; nothing on the page ever heard
back, and every test passed because it read the mock's keywords as one dict.

Name the frame with the keyword itself: ``session.msg(action_result=((), payload))``, or
``obj.msg(**{WebsocketMessageType.X.value: ((), payload)})``. ``# noqa: MSG_FRAME`` on the
call's line suppresses a hit and must say why.
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys

SUPPRESSION_TOKEN = "noqa: msg_frame"  # noqa: S105
_FRAME_SHAPED_KEYWORDS = frozenset({"type", "kwargs"})


def has_suppression(line: str) -> bool:
    """Return whether ``line`` carries the suppression token."""
    return SUPPRESSION_TOKEN in line.lower()


def check_source(source: str) -> list[tuple[int, int, str]]:
    """Return ``(lineno, col, keyword)`` for every ``.msg`` call given a frame-shaped keyword."""
    tree = ast.parse(source)
    lines = source.splitlines()
    hits: list[tuple[int, int, str]] = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "msg"
        ):
            continue
        for keyword in node.keywords:
            if keyword.arg not in _FRAME_SHAPED_KEYWORDS:
                continue
            if 0 < node.lineno <= len(lines) and has_suppression(lines[node.lineno - 1]):
                continue
            hits.append((keyword.value.lineno, keyword.value.col_offset, keyword.arg))
    return sorted(hits)


def check_file(path: Path) -> list[tuple[int, int, str]]:
    """Return the frame-shaped ``.msg`` keywords in the file at ``path``."""
    try:
        return check_source(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return []


def main(argv: list[str]) -> int:
    """Lint the given files; print each violation and return 1 if any were found."""
    failed = False
    for filename in argv:
        for lineno, col, keyword in check_file(Path(filename)):
            failed = True
            print(
                f"{filename}:{lineno}:{col + 1}: `.msg({keyword}=...)` sends a frame named "
                f"`{keyword}`; every keyword to msg is its own frame, so `type=` and `kwargs=` "
                "reach the client as two frames it never handles (#4774). Name the frame with "
                "the keyword: `msg(action_result=((), payload))`. Suppress with "
                "`# noqa: MSG_FRAME` plus a reason."
            )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
