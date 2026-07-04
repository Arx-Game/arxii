# ADR-0085: NpcRegard is a separate axis from NPCStanding

## Status

Accepted

## Context

`NpcRegard` (#1717) gives a notable NPC's `Persona` a signed opinion of another
persona (PC or NPC), an Organization, or a Society. `NPCStanding.affection`
(ADR-0058) is also a signed, durable, persona-keyed opinion value. Both could
represent "an NPC's opinion of a specific PC persona" — the overlap was
identified during #1717's design and needed a deliberate call rather than
silent duplication.

## Decision

Keep them as two separate models rather than merging or extending one into the
other:

- `NPCStanding` is scoped to a specific purpose: gating `NPCServiceOffer`
  eligibility predicates (`min_npc_standing`) for a **PC's** relationship with
  a named NPC. Its field naming (`persona` documented as "the PC's persona")
  and its existing callers assume a PC on one side.
- `NpcRegard` is a notable NPC's own declared stance toward **any** persona,
  an Organization, or a Society — authored by GMs, consumed by
  covenant/engagement logic (and future mission-antagonist/charm/parley
  consumers), with no offer-eligibility role at all.

Both happen to be signed integers with similar ranges; that surface similarity
is not enough to justify merging two models whose callers make different
assumptions about which side of the FK is a PC.

## Consequences

A future consumer that wants "this NPC's opinion of a specific PC" has two
places to check depending on intent: `NPCStanding.affection` for
offer-eligibility-flavored reads, `NpcRegard`/`get_regard` for
covenant/engagement/narrative-stance reads. This is a deliberate, documented
seam, not an accident — revisit only if a concrete consumer needs both to be
the same row.
