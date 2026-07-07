# ADR-0098: Dramatic surges are curve-gated, event-driven, one lever, generic narration

**Status:** Accepted

## Context

#2013 asked for three new combat triggers (mortal peril, hated foe, high stakes) to make
`CharacterEngagement.intensity_modifier` jump discontinuously at dramatic beats, on top of the
existing #872 grief spike (`apply_relationship_escalation_spike`).

## Decision

Every surge writes the ONE existing intensity lever through a single shared primitive
(`apply_dramatic_surge`), stays curve-gated (only encounters with an `escalation_curve` can
surge — matching #872's opt-in design), and is narrated generically (never naming the bond,
track, or subject — the leak rule). A `DramaticSurgeRecord` audit row (two partial
`UniqueConstraint`s, the `NpcRegard` NULL=NULL precedent) makes every trigger leg one-shot per
(encounter, participant, trigger_kind, subject) without ad hoc per-leg bookkeeping.

## Alternatives rejected

- **Uncapped, always-on surges** (no curve gate) — breaks the #872 opt-in escalation model;
  every fight would surge, defeating the "discontinuous jump, not a slope" premise.
- **`DramaticMomentTag`-driven live power** — that model is GM-manual and backward-looking
  (a post-hoc reward), the causality this feature needs is the opposite direction; left
  unchanged per the issue's non-goals.
- **Reading `NpcRegard`** for the hated-foe leg — wrong direction (the NPC's opinion of the PC,
  not the PC's hatred of the NPC); the PC's own negative-sign `CharacterRelationship` is correct.
