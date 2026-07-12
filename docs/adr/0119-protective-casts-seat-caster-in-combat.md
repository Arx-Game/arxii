# ADR-0119: Protective casts at embattled allies seat the caster in combat

**Date:** 2026-07-12
**Status:** Accepted
**Context:** #2226

## Context

Before #2226, the only paths by which a cast seated a non-participant in a live
`CombatEncounter` were:

1. **Hostile cast** → `seed_or_feed_encounter_from_cast` (pre-existing).
2. **Technique entrance** (#2183) → `seed_or_feed_encounter_from_benign_intervention`,
   called only from the entrance path.

An ordinary (non-entrance) protective cast at an embattled ally resolved via
`_route_immediate_cast` — it applied its effect but touched no combat state. The
caster was not seated in the encounter, not made targetable, and acknowledged no
risk. This let a caster support from total safety: casting a shield onto someone
mid-melee without any combat consequence.

The mechanical seam (`seed_or_feed_encounter_from_benign_intervention`) already
existed and was trivially callable from the general benign-cast path. The
question was whether to generalize it.

## Decision

Generalize benign-intervention combat seating to **all** protective casts. Any
benign (non-hostile) technique cast that affects an ACTIVE combatant seats the
caster in that combatant's encounter — regardless of targeting mode (SINGLE, AREA,
FILTERED_GROUP) or consent path (immediate or consent-requiring).

The cast's effect still applies normally. The seating is a post-resolution
side-effect, not a pre-cast gate. The caster is seated once per cast, even if
the technique touched multiple embattled allies.

Risk acknowledgement is automatic (`acknowledge_encounter_risk`), not a consent
gate. The caster chose to cast at someone in a fight; the risk acknowledgement
records that choice.

## Rejected alternatives

- **Opt-in only (the status quo):** Total safety from support casting is an
  exploit of the benign/behavioral consent distinction (ADR-0024 gates consent
  on behavior-alteration, not benign-vs-hostile). A protective shield is
  benign, so it resolves consent-free — but letting it affect combat without
  consequence is an oversight, not a design.
- **Offer-to-join prompt:** Preserves the deliberate-act principle but leaves
  the safe-distance gap open if the caster declines. The caster already chose
  to cast at a fighter; a second prompt is redundant friction.

## Relationship to existing ADRs

- **ADR-0024 (consent gates behavior-altering effects):** Benign casts remain
  consent-free for the *target* (no behavioral agency lost). The combat
  consequence falls on the *caster* via automatic risk acknowledgement, not a
  consent gate — deliberate, because the caster chose to cast at someone in a
  fight.
- **ADR-0023 (PvP is structurally non-lethal):** Seating makes the caster
  targetable, but PvP remains non-lethal. The caster risks defeat/yield, not
  death.
- **ADR-0113 (entrance carries the cast):** #2183's entrance-path seating is
  now a special case of the generalized rule. The entrance path's other hooks
  (flourish, disposition, suggestion) remain entrance-only; only the seating
  generalized.

## Consequences

- The `seat_caster_for_benign_intervention` wrapper (in `cast_seed.py`) iterates
  target sheets and calls the existing `seed_or_feed_encounter_from_benign_intervention`
  for each until one returns non-None. It excludes the caster's own sheet
  (self-cast is not intervention).
- `_route_immediate_cast` calls `_maybe_seat_caster_after_benign_cast` after the
  cast resolves. `CastResult.combat_seated` signals whether seating occurred.
- `resolve_accepted_cast` calls `_maybe_seat_after_consent_accept` after the
  benign consent-accept resolution. Both paths guard on `success_level > 0`.
- The entrance-path seating calls in `_run_entrance_benign_accept_hooks` and
  `EntranceAction._resolve_inline_entrance_result` are removed — the generalized
  calls supersede them.
