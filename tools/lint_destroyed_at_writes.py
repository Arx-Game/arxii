"""Reject a write to ``ItemInstance.destroyed_at`` outside the canonical destroy helper (#4099).

Soft-deleting an item is more than stamping ``destroyed_at``. The canonical rule,
``destroy_consumed_item_instance`` in ``src/world/items/services/usage.py``, also does
the following:
- clears the holder and the container (a destroyed item is held by nobody);
- unequips the item;
- spills a container's contents;
- takes the game object out of play;
- writes the exit ``OwnershipEvent`` that keeps the last holder.

Three paths hand-rolled the stamp and skipped the rest: the fence, ``recycle_item`` and
``redeem_favor_token``. Each left a destroyed row its old holder could still list, trade
or fence for a second payout. This lint catches the shape: any assignment to
``<x>.destroyed_at``, or a ``destroyed_at=`` keyword inside an ``.update(``,
``.create(``, ``.get_or_create(``, ``.update_or_create(`` or ``.bulk_update(`` call,
anywhere except ``world/items/services/usage.py``.

Suppress with ``# noqa: DESTROYED_AT <reason>`` on the flagged line. A bare token with
no reason is still a finding.
"""

from __future__ import annotations

import ast
from pathlib import Path
import re
import sys

FIELD = "destroyed_at"
ALLOWED_SUFFIX = "world/items/services/usage.py"
WRITE_CALLS = frozenset({"update", "create", "get_or_create", "update_or_create", "bulk_update"})
SUPPRESSION = re.compile(r"#\s*noqa:\s*DESTROYED_AT\b(?P<reason>.*)$", re.IGNORECASE)


def _suppressed(line: str) -> bool:
    """A suppression counts only when it gives a reason after the token."""
    match = SUPPRESSION.search(line)
    if match is None:
        return False
    return bool(match.group("reason").strip(" -:\t"))


def _targets(node: ast.AST) -> list[ast.expr]:
    if isinstance(node, ast.Assign):
        return list(node.targets)
    if isinstance(node, ast.AugAssign | ast.AnnAssign):
        return [node.target]
    return []


def _flattened(target: ast.expr) -> list[ast.expr]:
    if isinstance(target, ast.Tuple | ast.List):
        return [leaf for element in target.elts for leaf in _flattened(element)]
    return [target]


def check_source(source: str) -> list[tuple[int, int]]:
    """Return ``(line, col)`` for every unsuppressed ``destroyed_at`` write."""
    tree = ast.parse(source)
    lines = source.splitlines()
    hits: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        hits.extend(
            (leaf.lineno, leaf.col_offset)
            for target in _targets(node)
            for leaf in _flattened(target)
            if isinstance(leaf, ast.Attribute) and leaf.attr == FIELD
        )
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in WRITE_CALLS
        ):
            hits.extend(
                (keyword.value.lineno, keyword.value.col_offset)
                for keyword in node.keywords
                if keyword.arg == FIELD
            )
    return sorted(
        (line, col)
        for line, col in set(hits)
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
                f"{filename}:{lineno}:{col + 1}: writes `destroyed_at` outside the canonical "
                "destroy helper (#4099). Call `destroy_consumed_item_instance` "
                "(world/items/services/usage.py): it also clears holder and container, "
                "unequips, spills contents, and writes the exit OwnershipEvent. Suppress "
                "only with `# noqa: DESTROYED_AT <reason>`."
            )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
