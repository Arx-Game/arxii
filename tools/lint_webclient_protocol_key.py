"""Reject the protocol-key literals ``"webclient/websocket"`` and ``"webclient/ajax"`` (#4418).

Evennia's portal sets a web protocol instance's key to ``"webclient/websocket"`` in
``__init__``, then ``init_session("websocket", ...)`` overwrites it. A live browser
session's ``protocol_key`` is ``"websocket"`` (``"ajax/comet"`` for the AJAX fallback);
no live session ever carries the ``webclient/...`` spelling. ``non_web_sessions`` decided
"web" by a ``"webclient"`` prefix, so every real browser counted as non-web and every
telnet-only line reached browsers as a note, while every test passed because its fake
sessions used the ``"webclient/websocket"`` key no real session has.

Use ``world.scenes.interaction_services.WEB_PROTOCOL_KEYS`` (or its members) for the real
keys. A string literal containing either dead spelling, tests included, is rejected.
Docstrings are skipped; a comment is not a string literal. ``# noqa: WEBCLIENT_KEY`` on the
line suppresses a hit and must say why (for example a test that proves a dead key is
rejected).
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys

SUPPRESSION_TOKEN = "noqa: webclient_key"  # noqa: S105
_DEAD_KEYS = ("webclient/websocket", "webclient/ajax")


def has_suppression(line: str) -> bool:
    """Return whether ``line`` carries the suppression token."""
    return SUPPRESSION_TOKEN in line.lower()


def _docstring_nodes(tree: ast.Module) -> set[int]:
    """Return ids of the Constant nodes that are module, class or function docstrings."""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
            and ast.get_docstring(node, clean=False) is not None
        ):
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                ids.add(id(first.value))
    return ids


def check_source(source: str) -> list[tuple[int, int]]:
    """Return ``(lineno, col)`` for every string literal holding a dead web key."""
    tree = ast.parse(source)
    lines = source.splitlines()
    docstrings = _docstring_nodes(tree)
    hits: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        if id(node) in docstrings or not any(key in node.value for key in _DEAD_KEYS):
            continue
        if 0 < node.lineno <= len(lines) and has_suppression(lines[node.lineno - 1]):
            continue
        hits.append((node.lineno, node.col_offset))
    return sorted(hits)


def check_file(path: Path) -> list[tuple[int, int]]:
    """Return the dead-key literals in the file at ``path``."""
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
                f"{filename}:{lineno}:{col + 1}: `webclient/websocket` and `webclient/ajax` "
                "are keys no live web session carries (the portal overwrites them with "
                '`"websocket"` / `"ajax/comet"` at session creation), so code or a fake '
                "using them is wrong against real sessions (#4418). Use "
                "`world.scenes.interaction_services.WEB_PROTOCOL_KEYS`. Suppress with "
                "`# noqa: WEBCLIENT_KEY` plus a reason."
            )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
