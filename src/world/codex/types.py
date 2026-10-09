"""Typed value objects for the codex app."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CharacterKnowledge:
    """One character's knowledge of one codex entry, for API display.

    Built by the codex viewsets from ``CharacterCodexKnowledge`` rows scoped
    to the requesting account's characters, and consumed by the entry
    serializers to render per-character knowledge (the ``known_by`` field)
    without further queries.
    """

    roster_entry_id: int
    character_name: str
    status: str
    learning_progress: int


@dataclass(frozen=True)
class CompanionReader:
    """Who is reading an entry, as far as a companion provider needs to know (#4198).

    ``visible_entry_ids`` is the set the view already computed
    (``CodexVisibilityMixin._visible_entry_ids``: every entry for staff); a provider
    draws a line to another entry only when its id is here.
    """

    visible_entry_ids: frozenset[int]
    is_staff: bool

    def may_see(self, entry_id: int | None) -> bool:
        return entry_id is not None and entry_id in self.visible_entry_ids


@dataclass(frozen=True)
class CompanionItem:
    """One rail line: a fact, optionally a link to another entry or to a section below."""

    text: str
    entry_id: int | None = None
    anchor: str | None = None


@dataclass(frozen=True)
class CompanionGroup:
    label: str
    items: list[CompanionItem]


@dataclass(frozen=True)
class CompanionSection:
    """A paragraph under the Lore: a feast day's story, a god's side of a feud."""

    anchor: str
    label: str
    name: str
    body: str
    when: str | None = None
    entry_id: int | None = None


@dataclass(frozen=True)
class Companion:
    """What an entry's owner shows beside the prose (#4198): rail groups and sections."""

    rail: list[CompanionGroup]
    sections: list[CompanionSection]
