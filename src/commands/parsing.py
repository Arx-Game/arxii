"""Shared parsing utilities for command text."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from commands.exceptions import CommandError

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


# Matches comma-separated @name tokens at the start of text, e.g. "@bob,@carol waves"
_TARGET_PREFIX_RE = re.compile(
    r"^((?:@[\w-]+(?:\s*,\s*@[\w-]+)*))\s+(.*)",
    re.DOTALL,
)


def parse_targets_from_text(
    text: str,
    location: ObjectDB,
) -> tuple[str, list[ObjectDB]]:
    """Extract @name targets from the start of command text.

    Parses comma-separated @name tokens at the beginning of the text.
    Resolves each name against characters in the location.

    Known limitation: multi-word character names (e.g. "Crucible Mundi")
    cannot be parsed from ``@Crucible Mundi`` because the space terminates
    the token. The frontend autocomplete inserts single-token names that
    work correctly; manual typing of multi-word @targets is not supported.
    Hyphens and underscores are accepted within tokens (``@Crucible-Mundi``).

    Args:
        text: The raw command text, e.g. "@bob,@carol waves hello".
        location: The room to resolve names against.

    Returns:
        (remaining_text, resolved_targets) — remaining text has the
        @prefix stripped. Unresolved names are silently skipped.
    """
    if not text.startswith("@"):
        return text, []

    match = _TARGET_PREFIX_RE.match(text)
    if not match:
        return text, []

    target_part = match.group(1)
    remaining = match.group(2).strip()

    # Parse comma-separated @names
    target_names = [
        name.strip().lstrip("@") for name in target_part.split(",") if name.strip().startswith("@")
    ]

    # Resolve names against room contents (case-insensitive)
    targets: list[ObjectDB] = []
    for name in target_names:
        lower_name = name.lower()
        for obj in location.contents:
            if obj.db_key.lower() == lower_name:
                targets.append(obj)
                break

    return remaining, targets


def parse_kv_and_flags(
    rest: str,
    *,
    multiword_keys: frozenset[str],
    known_flags: frozenset[str],
) -> tuple[dict[str, str], set[str]]:
    """Split ``[key=value ...] [flag ...]`` into a kwargs dict + a flags set.

    A multiword key (in ``multiword_keys``) consumes tokens until the next
    ``key=`` token OR a known bare flag (in ``known_flags``) — so
    ``body=Hello public`` yields body="Hello" and sets the ``public`` flag,
    rather than absorbing the flag into the body. Bare tokens with no ``=`` are
    flags (if known) or an error.
    """
    tokens = rest.split()
    kwargs: dict[str, str] = {}
    flags: set[str] = set()
    key = ""
    value_parts: list[str] = []
    for token in tokens:
        if "=" in token and not token.startswith("="):
            if key:
                kwargs[key] = " ".join(value_parts).strip()
            key, _, value = token.partition("=")
            value_parts = [value] if value else []
        elif key and key in multiword_keys and token in known_flags:
            kwargs[key] = " ".join(value_parts).strip()
            key = ""
            value_parts = []
            flags.add(token)
        elif key and key in multiword_keys:
            value_parts.append(token)
        elif key:
            if token in known_flags:
                flags.add(token)
            else:
                msg = (
                    f"Unexpected argument '{token}' after '{key}='. "
                    "Multi-word values are only allowed for the multi-word keys."
                )
                raise CommandError(msg)
        elif token in known_flags:
            flags.add(token)
        else:
            msg = f"Unexpected argument '{token}'."
            raise CommandError(msg)
    if key:
        kwargs[key] = " ".join(value_parts).strip()
    return kwargs, flags
