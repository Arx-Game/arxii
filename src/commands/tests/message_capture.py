"""Read the text of a captured ``msg`` call, whatever form it took (#3856).

Commands send their lines in one of two shapes: a bare string, or Evennia's
tuple form ``(text, {"type": kind})`` when the line is typed for the web feed
(a look result, an item line, every error). Tests that capture ``caller.msg``
with a lambda and then search the text (``"no such trap" in m.lower()``) need
the text either way; this is the one place that knows both shapes.
"""

from __future__ import annotations


def message_text(first: object) -> str:
    """Return the text of a ``msg`` call's first positional argument."""
    if isinstance(first, tuple):
        return str(first[0])
    return str(first)
