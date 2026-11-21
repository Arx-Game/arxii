"""Reject a player-facing read of Interaction rows that skips the block check (#3751).

``InteractionQuerySet.visible_to`` answers "may this account read the row", and nothing
more. A player's read must also drop the faces their blocks hide, which is
``InteractionQuerySet.readable_by`` (``visible_to`` plus the block exclusion). Three
places called ``visible_to`` alone and reached main: a reply's parent chip leaked a blocked
author's pose id and timestamp, the top-bar badge counted a blocked author's whispers, and
the reply-target and nomination checks accepted a blocked author's pose by id.

The rule: no production module outside ``world/scenes/managers.py`` calls ``.visible_to(``.
Use ``readable_by``. Use ``# noqa: VISIBLE_TO`` on the call's own line, with a reason, only
for a call that is not a player read (a staff-only tool, or a system process with no viewer);
"I did not need blocks here" is not a reason.
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys

SUPPRESSION_TOKEN = "noqa: visible_to"  # noqa: S105
OWNER_MODULE = "world/scenes/managers.py"


def has_suppression(line: str) -> bool:
    """Return whether ``line`` carries the suppression token."""
    return SUPPRESSION_TOKEN in line.lower()


def check_source(source: str) -> list[tuple[int, int]]:
    """Return ``(line, col)`` for every unsuppressed ``.visible_to(`` call."""
    lines = source.splitlines()
    errors: list[tuple[int, int]] = []
    for node in ast.walk(ast.parse(source)):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "visible_to"
        ):
            continue
        line_index = node.lineno - 1
        if line_index < len(lines) and has_suppression(lines[line_index]):
            continue
        errors.append((node.lineno, node.col_offset))
    return sorted(errors)


def check_file(path: Path) -> list[tuple[int, int]]:
    """Return the findings in the file at ``path``; the queryset's own module is exempt."""
    if path.as_posix().endswith(OWNER_MODULE):
        return []
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
                f"{filename}:{lineno}:{col + 1}: `.visible_to(` answers whether a row may be "
                "read and ignores the viewer's blocks (#3751). Use "
                "`Interaction.objects.readable_by(...)`, or suppress with "
                "`# noqa: VISIBLE_TO` plus a reason only when this is not a player read."
            )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
