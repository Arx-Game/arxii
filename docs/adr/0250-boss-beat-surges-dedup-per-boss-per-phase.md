# ADR-0250: A boss beat's surge dedups per boss per phase, not per encounter

**Status:** Accepted

## Context

#3445 wired the boss anatomy (phase transitions, enrage, break bar) into the escalation
engine, which had never seen it: no `SurgeTriggerKind` keyed off a boss event, so the
loudest authored beats a fight has left every PC's `intensity_modifier` untouched.

ADR-0098 made every surge one-shot per `(encounter, participant, trigger_kind,
subject_sheet)`. That key cannot express a boss beat. A boss opponent is a
`CombatOpponent` and generally carries `persona=None`, so `subject_sheet` cannot name it,
and with the subject null the key collapses to one surge per kind per encounter - which
would leave a three-phase boss surging only at its first transition.

## Decision

`DramaticSurgeRecord` gains a nullable `subject_opponent` FK and a nullable
`subject_phase_number`, plus a third partial `UniqueConstraint` covering the boss slice.
A boss beat therefore dedups on `(encounter, participant, trigger_kind, subject_opponent,
subject_phase_number)`: each phase transition surges, and each phase's first break surges.
`unique_surge_without_subject` narrows to `subject_sheet IS NULL AND subject_opponent IS
NULL`, so `HIGH_STAKES` and `GM_MANUAL` stay one-shot per encounter exactly as before.
Two `CheckConstraint`s keep the slices disjoint and the key total.

The discriminator is the boss's `current_phase`, not `round_number`, because #2642's
break bar stays at zero once broken and re-opens its vulnerability window every round a
qualifying feed lands. On a round key the break surge would re-fire indefinitely; on a
phase key it fires once per phase and again only when a transition re-stamps the bar.

This extends ADR-0098 rather than superseding it: one lever, one write path
(`apply_dramatic_surge`), curve-gated, generically narrated.

## Alternatives rejected

- **Once per encounter per kind** (no schema change) - a three-phase boss surges once and
  phases two and three are silent, which is most of the drama #3445 exists to add.
- **`round_number` as the discriminator** - re-fires the break surge every round of the
  #2642 re-break loop.
- **An FK to `BossPhase`** - a boss's `current_phase` is always defined (default 1) while a
  `BossPhase` row is not guaranteed for every boss, so the FK would be null exactly where
  the dedup key needs a value.
- **`SET_NULL` on `subject_opponent`** - nulling it drops the row into the subject-less
  slice of the unique index and can raise `IntegrityError` on delete. CASCADE loses no
  audit history in practice: nothing deletes a `CombatOpponent` in production.
- **Per-boss / per-phase authored magnitudes** (on `BossPhase` / `BreakBarConfig`) - splits
  escalation tuning across two authoring surfaces and leaves generic bosses at zero unless
  every phase row is filled in. Magnitudes stay on `EscalationCurve` with the other five
  trigger amounts.
