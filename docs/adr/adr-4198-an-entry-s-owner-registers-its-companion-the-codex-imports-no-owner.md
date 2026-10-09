# ADR-4198: An entry's owner registers its companion; the Codex imports no owner

**Status:** Accepted (2026-10-08, ApostateCD)
**Issue:** #4198
**Related:** ADR-0010 (FK direction, specific → general), ADR-0221 (entries are the unit of
secrecy), ADR-0132 (gods as authorable data)

## Context

The deity editor writes a god's domains, names, feast days, cards, resonances, facets and
relationships, and the Codex page showed none of it: only the quote reached the reader. The
same gap waits for every other thing an entry is about (a card, a gift, a species). The
facts belong beside the prose, in the reader's view of the entry; the rows belong to their
owners.

## Decision

A Codex entry carries a **companion**: a rail of labelled groups beside the Lore and
sections of prose under it, serialized on retrieve as
`CodexEntryDetailSerializer.companion`. `world/codex/companions.py` is a registry;
each owning sub-package registers a provider `(entry, reader) -> Companion | None` from its
`ready()`, through `world/apps.py`'s hook order, and the view asks every provider and takes
the first answer. The Codex never imports an owner: the specific side (worship) points at the
general one (codex), as ADR-0010 has it for foreign keys.

The reader the view hands over already holds the visibility decision
(`CodexVisibilityMixin._visible_entry_ids`, everything for staff). A provider draws a line to
another entry only when that entry is in the set, so a feud with a god the reader cannot see
is not drawn at all, not as a line and not as a section: the relationship would otherwise
reveal that the other god exists. The companion also rides the prose's research gate: an
entry still being researched shows its summary alone.

Two schema changes ride along because the companion is the first reader of the rows and
found them short: the being↔card link becomes a row with an orientation
(`BeingTarotCard.is_reversed`, the auto M2M table adopted in place), and a relationship
carries a story per side (`story_from_a`, `story_from_b`), each god's page writing and
showing its own.

## Alternatives rejected

- **The Codex serializer reaches into worship.** One import today, every owner tomorrow;
  the general model would depend on each system that points at it (the inversion ADR-0010
  forbids).
- **A generic "related rows" dump.** The reader wants a date, a name, a card, a link; the
  owner knows which rows read as which, and in what order.
- **Showing a relationship line with the other god's name unlinked when its entry is
  hidden.** The name alone leaks the god's existence; ruled out with ApostateCD on the demo.
- **A reversed card as a second card row.** The pair is one belief with an orientation;
  `TarotCard.get_surname(is_reversed)` already treats reversal as a flag, and a unique on
  (being, card) keeps a card from being held both ways.
- **The rail in the Codex modal too.** The modal is a small window for a look-up; the full
  page is one click away.

## Consequences

Any owner can give its entries a companion without touching `codex`; the deity's is the
only provider in #4198. The companion's cost is the owner's queries on retrieve only (one
per satellite table, none on list). Every IC date a player reads now spells
"Masquing 18 (10/18)" through the one formatter, so the feast-day line, birthdays,
journals, events and the relationship stream moved together.
