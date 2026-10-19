"""Reject deleting an item's game object or ItemInstance outside the usage helpers (#4474).

``ItemInstance.game_object`` is a ``OneToOneField(ObjectDB, on_delete=CASCADE)``, so
deleting an item's game object deletes the item row with its ownership history and
design. Vault custody, evidence disposal and coin redemption each did that by hand and
skipped the destroy rules (soft-delete for an item with a design or provenance, the exit
``OwnershipEvent``, the holder's inventory cache). Two helpers in
``src/world/items/services/usage.py`` own the deletion:
- ``dematerialize_item_instance`` drops only the object and keeps the item;
- ``destroy_consumed_item_instance`` (and ``hard_delete_item_instance`` under it) destroys
  the item by the rules.

This lint flags, anywhere except ``usage.py``, a ``.delete()`` whose receiver is a
``.game_object`` attribute or a variable named ``game_object``, and a ``.delete()`` on a
chain rooted at ``ItemInstance`` (``ItemInstance.objects.filter(...).delete()``).
``cleanup.py`` calls ``hard_delete_item_instance``, so it needs no carve-out. Deleting
the object of something that is not an item (a room, a character) is a different matter:
name the variable something else, or suppress with ``# noqa: ITEM_DELETE <reason>``. A
bare token with no reason is still a finding.
"""

from __future__ import annotations

import ast
from pathlib import Path
import re
import sys

ALLOWED_SUFFIX = "world/items/services/usage.py"
SUPPRESSION = re.compile(r"#\s*noqa:\s*ITEM_DELETE\b(?P<reason>.*)$", re.IGNORECASE)


def _suppressed(line: str) -> bool:
    """A suppression counts only when it gives a reason after the token."""
    match = SUPPRESSION.search(line)
    if match is None:
        return False
    return bool(match.group("reason").strip(" -:\t"))


def _root_name(node: ast.expr) -> str | None:
    """The leftmost bare name of an attribute/call chain, or None."""
    while True:
        if isinstance(node, ast.Attribute):
            node = node.value
        elif isinstance(node, ast.Call):
            node = node.func
        elif isinstance(node, ast.Name):
            return node.id
        else:
            return None


def _is_item_delete(receiver: ast.expr) -> bool:
    if isinstance(receiver, ast.Attribute) and receiver.attr == "game_object":
        return True
    if isinstance(receiver, ast.Name) and receiver.id == "game_object":
        return True
    return _root_name(receiver) == "ItemInstance"


def check_source(source: str) -> list[tuple[int, int]]:
    """Return ``(line, col)`` for every unsuppressed item delete."""
    tree = ast.parse(source)
    lines = source.splitlines()
    hits = [
        (node.lineno, node.col_offset)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "delete"
        and _is_item_delete(node.func.value)
    ]
    return sorted(
        (line, col)
        for line, col in hits
        if not (line - 1 < len(lines) and _suppressed(lines[line - 1]))
    )


def check_file(path: Path) -> list[tuple[int, int]]:
    """Return the findings for the file at ``path`` (none for the canonical module)."""
    if path.as_posix().endswith(ALLOWED_SUFFIX):
        return []
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
                f"{filename}:{lineno}:{col + 1}: deletes an item's game object or "
                "ItemInstance outside the usage helpers (#4474). The game object cascades "
                "to the item row. Use `dematerialize_item_instance` to keep the item, or "
                "`destroy_consumed_item_instance` to destroy it "
                "(world/items/services/usage.py). Suppress only with "
                "`# noqa: ITEM_DELETE <reason>`."
            )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
