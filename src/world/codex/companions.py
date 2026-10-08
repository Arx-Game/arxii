"""The companion registry (#4198, ADR-4198).

A Codex entry is prose; the thing it is about (a god today, a tradition or a card
tomorrow) holds facts the entry should show beside the prose: dates, names, cards,
who it feuds with. The Codex does not know its owners (ADR-0010: the specific side
points at the general one), so each owning sub-package registers a provider at
``ready()`` and the entry view asks every provider on retrieve, taking the first
answer. A provider answers ``None`` for an entry it does not own.

The reader the view hands over already carries the visibility decision: a provider
draws a line to another entry only when that entry's id is in
``CompanionReader.visible_entry_ids`` (for staff, every entry), so the companion can
never name a thing the prose could not.
"""

from __future__ import annotations

from collections.abc import Callable

from world.codex.models import CodexEntry
from world.codex.types import Companion, CompanionReader

CompanionProvider = Callable[[CodexEntry, CompanionReader], "Companion | None"]

_PROVIDERS: list[CompanionProvider] = []


def register_companion(provider: CompanionProvider) -> None:
    """Called from an owner's ``ready()``; registering twice is a no-op."""
    if provider not in _PROVIDERS:
        _PROVIDERS.append(provider)


def companion_for(entry: CodexEntry, reader: CompanionReader) -> Companion | None:
    """The first registered owner's companion for ``entry``, or ``None``."""
    for provider in _PROVIDERS:
        companion = provider(entry, reader)
        if companion is not None:
            return companion
    return None
