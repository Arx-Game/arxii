"""Shared parsing utilities for command text."""

from __future__ import annotations

from dataclasses import dataclass, field
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

    # Resolve names against room contents (case-insensitive) — shared with the REST
    # submit-pose `target_names` field so a directed pose resolves identically
    # regardless of which surface sent it (#2156).
    from world.scenes.interaction_services import resolve_characters_by_name  # noqa: PLC0415

    targets = resolve_characters_by_name(target_names, location)

    return remaining, targets


@dataclass
class _KvParseState:
    """Mutable accumulator for ``parse_kv_and_flags`` as it walks the tokens."""

    kwargs: dict[str, str] = field(default_factory=dict)
    flags: set[str] = field(default_factory=set)
    key: str = ""
    value_parts: list[str] = field(default_factory=list)

    def flush_key(self) -> None:
        """Commit the active key's accumulated value into ``kwargs`` (if any key)."""
        if self.key:
            self.kwargs[self.key] = " ".join(self.value_parts).strip()


def _consume_bare_token(
    token: str,
    state: _KvParseState,
    multiword_keys: frozenset[str],
    known_flags: frozenset[str],
) -> None:
    """Apply a token with no leading ``key=`` to *state*, mutating it in place.

    A bare known flag ends an active multi-word key (flushing it) and is
    recorded; otherwise it is appended to a multi-word value, recorded as a flag
    for a non-multiword key, or rejected.
    """
    key = state.key
    if key and key in multiword_keys:
        if token in known_flags:
            state.flush_key()
            state.flags.add(token)
            state.key = ""
            state.value_parts = []
        else:
            state.value_parts.append(token)
        return
    if key:
        if token not in known_flags:
            msg = (
                f"Unexpected argument '{token}' after '{key}='. "
                "Multi-word values are only allowed for the multi-word keys."
            )
            raise CommandError(msg)
        state.flags.add(token)
        return
    if token in known_flags:
        state.flags.add(token)
        return
    msg = f"Unexpected argument '{token}'."
    raise CommandError(msg)


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
    state = _KvParseState()
    for token in rest.split():
        if "=" in token and not token.startswith("="):
            state.flush_key()
            state.key, _, value = token.partition("=")
            state.value_parts = [value] if value else []
        else:
            _consume_bare_token(token, state, multiword_keys, known_flags)
    state.flush_key()
    return state.kwargs, state.flags
