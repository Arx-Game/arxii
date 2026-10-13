"""Reject reading or writing Evennia's ``desc`` Attribute (#4329).

An object's description has one store, ``ObjectDisplayData.permanent_description``,
which ``look`` reads for rooms, objects and exits (a character's is its sheet's
``additional_desc``). Evennia keeps a second, the ``desc`` Attribute, and its own
code still uses it: the stock ``desc`` command wrote it and the stock post-move look
read it. Nothing of ours renders it, so text written there is invisible, and text
read from there is whatever a stock path left behind. #4329 found staff ``desc``
reporting success while ``look`` never changed, two seeds whose text never showed,
and every room the builder made arriving as "This is a room."

This lint catches the shape in our code: ``<x>.db.desc`` in any position (read,
assignment, delete), and ``<x>.attributes.get|add|remove|has("desc", ...)``.

Suppress with ``# noqa: EVENNIA_DESC <reason>`` on the flagged line. A bare token
with no reason is still a finding.
"""

from __future__ import annotations

import ast
from pathlib import Path
import re
import sys

ATTRIBUTE_KEY = "desc"
ATTRIBUTE_HANDLER_METHODS = frozenset({"get", "add", "remove", "has"})
SUPPRESSION = re.compile(r"#\s*noqa:\s*EVENNIA_DESC\b(?P<reason>.*)$", re.IGNORECASE)


def _suppressed(line: str) -> bool:
    """A suppression counts only when it gives a reason after the token."""
    match = SUPPRESSION.search(line)
    if match is None:
        return False
    return bool(match.group("reason").strip(" -:\t"))


def _is_db_desc(node: ast.AST) -> bool:
    """``<x>.db.desc``."""
    return (
        isinstance(node, ast.Attribute)
        and node.attr == ATTRIBUTE_KEY
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "db"
    )


def _is_handler_desc_call(node: ast.AST) -> bool:
    """``<x>.attributes.get("desc")`` and its add/remove/has siblings."""
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
        return False
    handler = node.func.value
    first = node.args[0] if node.args else None
    return (
        node.func.attr in ATTRIBUTE_HANDLER_METHODS
        and isinstance(handler, ast.Attribute)
        and handler.attr == "attributes"
        and isinstance(first, ast.Constant)
        and first.value == ATTRIBUTE_KEY
    )


def check_source(source: str) -> list[tuple[int, int]]:
    """Return ``(line, col)`` for every unsuppressed use of the ``desc`` Attribute."""
    tree = ast.parse(source)
    lines = source.splitlines()
    hits = {
        (node.lineno, node.col_offset)
        for node in ast.walk(tree)
        if _is_db_desc(node) or _is_handler_desc_call(node)
    }
    return sorted(
        (line, col)
        for line, col in hits
        if not (line - 1 < len(lines) and _suppressed(lines[line - 1]))
    )


def check_file(path: Path) -> list[tuple[int, int]]:
    """Return the findings for the file at ``path``."""
    try:
        return check_source(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return []


def main(argv: list[str]) -> int:
    """Lint the given files; print each finding and return 1 if any were found."""
    failed = False
    for filename in argv:
        for lineno, col in check_file(Path(filename)):
            failed = True
            print(
                f"{filename}:{lineno}:{col + 1}: uses Evennia's `desc` Attribute, which "
                "nothing renders (#4329). A room's, object's or exit's description is "
                "ObjectDisplayData.permanent_description: write it with "
                "evennia_extensions.services.display.set_permanent_description and read it "
                "with item_data.get_display_description(). A character's is its sheet's "
                "(world.character_sheets.services.set_physical_description); an item's is "
                "its ItemInstance's custom_description. Suppress only with "
                "`# noqa: EVENNIA_DESC <reason>`."
            )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
