"""Shared parsing utilities for command text."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

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
