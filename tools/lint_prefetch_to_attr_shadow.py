"""Reject a ``Prefetch`` whose ``to_attr`` repeats the relation it prefetches (#4418).

``Prefetch("trait_lines", queryset=..., to_attr="trait_lines")`` asks Django to store
the rows under the relation's own name. Django refuses: the name is a field or reverse
accessor on the model, and it raises ``ValueError: to_attr=trait_lines conflicts with a
field on the NPCStatlinePreset model``. The raise happens on the first request that
evaluates the queryset, so a unit test that never lists the endpoint passes and the
endpoint is a 500. ``GET /api/roster/npc-presets/`` was one for as long as the
viewset had existed, and the staff form's stat block list stayed empty.

The check is the one shape that is always wrong and cheap to see: the last segment of
the lookup (``"a__b__trait_lines"`` -> ``trait_lines``) equal to the ``to_attr``
string. A ``to_attr`` that collides with some other field or property of the model
(``to_attr="name"``) needs the model, which a single-file AST pass does not have; that
wider shape is left to ``prefetch-to-attr-reviewer`` guidance in
``tools/agents/identity-map-write-reviewer.md`` and to the endpoint test every
``to_attr`` change must carry.

``# noqa: PREFETCH_SHADOW`` suppresses a hit, with a reason.
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys

SUPPRESSION_TOKEN = "noqa: prefetch_shadow"  # noqa: S105


def has_suppression(line: str) -> bool:
    """Return whether ``line`` carries the suppression token."""
    return SUPPRESSION_TOKEN in line.lower()


def _is_prefetch_call(node: ast.Call) -> bool:
    """Whether ``node`` is a ``Prefetch(...)`` call, however it was imported."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "Prefetch"
    return isinstance(func, ast.Attribute) and func.attr == "Prefetch"


def _string_value(node: ast.expr | None) -> str | None:
    """Return the string a node is a literal of, else None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _lookup(node: ast.Call) -> str | None:
    """Return the Prefetch's lookup string, positional or ``lookup=``."""
    if node.args:
        return _string_value(node.args[0])
    for keyword in node.keywords:
        if keyword.arg == "lookup":
            return _string_value(keyword.value)
    return None


def check_source(source: str) -> list[tuple[int, int]]:
    """Return ``(lineno, col)`` for every ``Prefetch`` whose to_attr repeats its lookup."""
    tree = ast.parse(source)
    lines = source.splitlines()
    hits: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _is_prefetch_call(node):
            continue
        lookup = _lookup(node)
        if lookup is None:
            continue
        for keyword in node.keywords:
            if keyword.arg != "to_attr" or _string_value(keyword.value) != lookup.split("__")[-1]:
                continue
            span = {keyword.value.lineno, node.lineno}
            if any(has_suppression(lines[n - 1]) for n in span if 0 < n <= len(lines)):
                continue
            hits.append((keyword.value.lineno, keyword.value.col_offset))
    return sorted(hits)


def check_file(path: Path) -> list[tuple[int, int]]:
    """Return the shadowing prefetches in the file at ``path``."""
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
                f"{filename}:{lineno}:{col + 1}: `to_attr` repeats the relation it "
                "prefetches. Django raises `ValueError: to_attr=... conflicts with a "
                "field` on first evaluation, so the endpoint is a 500 that a test which "
                "never lists it will not see (#4418). Prefetch onto a differently named "
                "`PrunedCachedProperty` (`cached_<relation>`). Suppress with "
                "`# noqa: PREFETCH_SHADOW` plus a reason."
            )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
