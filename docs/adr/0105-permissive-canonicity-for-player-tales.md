# ADR-0105: Permissive canonicity for player tales

## Status

Accepted (2026-07-08)

## Context

Mission runs produce mechanical outcomes (dice rolls, rewards, status changes).
Players want to narrate *how* their character experienced the run — the story
behind the mechanics. The question is whether to curate this narration or let
it flow freely.

The existing `LegendDeedStory` surface already established a precedent: free
text with no content gate, authored per persona per deed. Tales extend this to
every mission run, not just legend-minting ones.

## Decision

Adopt permissive canonicity: player narration of a mechanical success is canon
by default. Staff never pre-approve tales. Impossible elaborations are
non-canonical fabrications (braggadocio), handled in-world — not by moderation.
Tales are never parsed for mechanics and never content-gated.

The `docs/systems/narrative.md` "Player Tales" section is the player-facing
statement of this policy; this ADR records the trade-off.

## Rejected alternative

Staff curation queues: a review step where staff approve each tale before it
becomes canon. Rejected because it would bottleneck narrative flow, require
staffing for a primarily-flavor feature, and contradict the game's design goal
of player-driven narrative. The `save_deed_story` precedent (no content gate
on free-text deed stories) already established the pattern.
