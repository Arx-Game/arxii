"""Splitting command arguments on a keyword, without a backtracking regex.

`^(.+?)\\s+from\\s+(.+)$` and its siblings were spread across the telnet
commands. A lazy `.+?` followed by a literal makes the engine retry the literal
at every position, which is superlinear on input that never contains the keyword
(SonarCloud `python:S8786`). Splitting on the keyword does the same job in one
pass, and reads as what it is.
"""

from __future__ import annotations

import re


def split_on_keyword(args: str, keyword: str) -> tuple[str, str] | None:
    """Split ``"<left> <keyword> <right>"`` at the first keyword occurrence.

    Returns ``None`` when the keyword is absent or either side is empty, which is
    the same "no match" the regexes signalled. Matching is case-insensitive and
    the keyword must be surrounded by whitespace, so "from" inside a word does
    not split.

    Args:
        args: The raw argument string.
        keyword: The infix word to split on, e.g. ``"from"``.

    Returns:
        The trimmed left and right halves, or None.
    """
    parts = re.split(rf"\s+{re.escape(keyword)}\s+", args, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) != 2:  # noqa: PLR2004 - a split yields exactly two halves or it did not match
        return None
    left, right = parts[0].strip(), parts[1].strip()
    if not left or not right:
        return None
    return left, right


def strip_leading_word(args: str, word: str) -> str | None:
    """Return what follows ``word`` at the start of ``args``, or None.

    Replaces ``^word\\s+(.+)$``, where the `\\s+`/`(.+)` pair backtracks.
    """
    stripped = args.lstrip()
    if not stripped.lower().startswith(word.lower()):
        return None
    rest = stripped[len(word) :]
    if rest and not rest[0].isspace():
        return None  # a longer word that merely starts with `word`
    rest = rest.strip()
    return rest or None


def split_possessive(args: str) -> tuple[str, str] | None:
    """Split ``"alice's sword"`` into ``("alice", "sword")``.

    Scans for the first apostrophe rather than matching a pattern, so there is no
    backtracking to bound. Returns ``None`` when the string is not a possessive
    form, when either side is empty, or when the ``'s`` is not followed by
    whitespace (``"alice'sword"`` is one word, not a possessive).
    """
    marker = args.find("'")
    if marker <= 0:
        return None
    rest = args[marker + 1 :]
    if rest[:1].lower() != "s":
        return None
    rest = rest[1:]
    if not rest[:1].isspace():
        return None
    owner, item = args[:marker].strip(), rest.strip()
    if not owner or not item:
        return None
    return owner, item
