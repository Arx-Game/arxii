"""Small player-facing text helpers shared across systems."""

from __future__ import annotations

_VOWELS = frozenset("aeiou")


def with_indefinite_article(noun: str) -> str:
    """``noun`` with "a" or "an" before it, by its first letter: "an axe", "a rapier".

    A blank noun comes back blank. Spelling only: "an hour" and "a unicorn" are beyond it.
    """
    if not noun:
        return noun
    article = "an" if noun[0].lower() in _VOWELS else "a"
    return f"{article} {noun}"
