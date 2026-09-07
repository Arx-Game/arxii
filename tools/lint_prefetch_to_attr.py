"""Reject ``to_attr=`` prefetches; rows belong to a handler (#3673, ADR-0263).

``Prefetch(..., to_attr="x")`` writes a plain attribute into the instance
``__dict__``, and Django decides whether to run a prefetch by asking whether the
attribute is already there. Under the identity map (ADR-0008) every queryset
returns the same Python object for a pk for the life of the process, so the
first prefetch that sets ``x`` makes every later one onto that instance a silent
no-op: the second request re-serves the first request's rows. A row deleted in
between comes back with a null id, because ``Collector.delete()`` nulls the pk
on the shared instance it deleted.

A bare-string ``prefetch_related("x")`` is no safer - it goes stale the same way
through ``instance._prefetched_objects_cache`` - so the answer is neither
spelling. Rows a parent owns live behind a ``CachedRowsHandler``
(``evennia_extensions/handlers.py``): one place that loads them, one place that
drops rows whose pk has gone falsey, cleared by writers through
``related_cache_fields``, and batched for a list endpoint with ``prime()``.
Consumers - serializers, telnet commands, flows, service functions - read the
handler and stay ignorant of where the rows came from.

Use ``# noqa: PREFETCH_TO_ATTR`` to suppress, with a reason.
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys

SUPPRESSION_TOKEN = "noqa: prefetch_to_attr"  # noqa: S105


def has_suppression(line: str) -> bool:
    """Return whether ``line`` carries the suppression token."""
    return SUPPRESSION_TOKEN in line.lower()


def _is_prefetch_call(node: ast.Call) -> bool:
    """Whether ``node`` is a ``Prefetch(...)`` call, however it was imported."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "Prefetch"
    return isinstance(func, ast.Attribute) and func.attr == "Prefetch"


def check_source(source: str) -> list[tuple[int, int]]:
    """Return ``(lineno, col)`` for every unsuppressed ``to_attr=`` prefetch."""
    tree = ast.parse(source)
    lines = source.splitlines()
    hits: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _is_prefetch_call(node):
            continue
        for keyword in node.keywords:
            if keyword.arg != "to_attr":
                continue
            lineno = keyword.value.lineno
            # The suppression may sit on the keyword's own line or on the line
            # opening the Prefetch call, which is where a reader looks first.
            span = {lineno, node.lineno}
            if any(has_suppression(lines[n - 1]) for n in span if 0 < n <= len(lines)):
                continue
            hits.append((lineno, keyword.value.col_offset))
    return sorted(hits)


def check_file(path: Path) -> list[tuple[int, int]]:
    """Return the ``to_attr=`` prefetches in the file at ``path``."""
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
        for lineno, col in check_file(Path(filename)):
            failed = True
            print(
                f"{filename}:{lineno}:{col + 1}: `to_attr=` prefetch onto an identity-mapped "
                "instance. Django skips a prefetch whose to_attr is already set and the "
                "identity map hands the same instance to the next request, so this serves "
                "stale rows - including deleted ones, which arrive with a null id "
                "(ADR-0263, #3673). Put the rows behind a CachedRowsHandler "
                "(evennia_extensions/handlers.py) and read that instead; batch a list "
                "endpoint with its prime(). Suppress with `# noqa: PREFETCH_TO_ATTR` "
                "plus a reason."
            )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
