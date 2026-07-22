# Sent Flying clones the plummet pattern: marker + reactable window + explicit resolution; rescues celebrated, absences unremarked

#2638 asks for a general "consequence event in flight" grammar, seeded with its first
instance: a big NPC hit that launches its victim airborne. Rather than building new
machinery, this generalizes #1228's plummet system's own shape — a non-expiring marker
condition, a window during which the moment is reactable, and an explicit end-of-round
resolution — into a reusable template for future consequence events.

## Decision

**The marker owns its own lifetime; the generic duration engine never touches it.**
`ThreatPoolEntry.sends_flying` applies the seeded "Sent Flying" `ConditionTemplate` on a
damaging hit. Despite the design doc's "1-round marker" shorthand, the template's
`default_duration_type` is `PERMANENT` (`rounds_remaining=None`), NOT a literal
`ROUNDS`/`1` — the generic end-of-round duration countdown
(`tick_round_for_targets(timing="end")`) runs BEFORE the sent-flying resolution pass in
`resolve_round`, so a literal 1-round duration would auto-delete the marker before the
explicit resolution code ever saw it. This is the exact same reasoning `ensure_fall_content`
already documents for Plummeting — cloned, not reinvented.

**The catch is a budget gate, not a skill roll.** `_try_catch_sent_flying` reuses
`_try_interpose`'s query shape (an armed INTERPOSE this round, named or guard-anyone) but
never calls `dispatch_interpose` or the technique-guardian challenge chain — that
machinery grades HOW MUCH of a landing hit's amount a block reduces, which has no meaning
for a mid-air catch (a binary rescue). "Fires" means what
`_dispatch_interpose_action`'s own docstring already establishes: an attempt that clears
`REACTIONS_PER_ROUND`, independent of any roll. No new challenge/roll content is
authored — the armed declaration alone, already proven out by ADR-0118 and ADR-0156,
carries the mechanical weight.

**The plummet chain is a handoff, not a reimplementation.** An unanswered marker resolves
by asking the SAME question `maybe_emit_fall` already asks — does the victim's room have a
CHASM position? — and if so, force-moves them into it and calls `maybe_emit_fall`, which
hands off to the existing FELL trigger -> `begin_plummet` -> the full multi-round
descent + `CATCH_THE_FALLER` machinery. Zero new descent/catch code.

**The v1 damage carrier is a single field, not a new model.** `CombatParticipant.
sent_flying_damage` stamps the triggering hit's amount because the marker is
non-stackable — only one Sent Flying instance can ever be active on a participant, so a
single `PositiveIntegerField` (cleared to 0 on catch or landing) is sufficient. A
dedicated event/history model was rejected as premature generality for a v1 with exactly
one consequence type; if a second consequence event needs its own carrier shape, that is
the moment to generalize the field into something shared.

**Rescues are loud; absences are unremarked.** A caught marker celebrates the catcher (and
the wind-up's caller, if the source attack was called out) on both broadcast channels. An
unanswered marker's hard-landing impact — `floor(sent_flying_damage *
SENT_FLYING_IMPACT_FRACTION)` (0.5) as Physical damage through the standard
`apply_damage_to_participant` + `process_damage_consequences` path — gets NO extra
narration beyond whatever that standard path already produces. This mirrors the wind-up
family's own celebrate/silence boundary (ADR-0156): the game marks victories, not misses.

**Bug fix folded in, not filed:** while writing `_try_catch_sent_flying`'s query, mirroring
`_try_interpose`'s `focused_ally_target__in=[participant, None]` surfaced that Django
compiles a `None` member of an `__in` list to a bare `IN (x)`, silently dropping the `IS
NULL` branch — meaning a guard-anyone (`focused_ally_target=None`) declaration could never
actually fire through `_try_interpose`'s real damage-application query, even though
`ally_intercepted_for_me` and `_ensure_interpose_challenges` both correctly treat it as
armed cover. Both queries now use `Q(focused_ally_target=participant) |
Q(focused_ally_target__isnull=True)`.

## Rejected alternatives

- **A literal `ROUNDS`/`1` duration** — rejected: races the generic duration tick inside
  `resolve_round`, auto-removing the marker before explicit resolution runs (see above).
- **Routing the catch through `dispatch_interpose`'s mundane/technique challenge chain** —
  rejected: that machinery grades a damage-reduction amount; a mid-air catch is a binary
  rescue with no "amount" to grade, and authoring a new challenge/roll for it would
  violate the "no seed content beyond the mechanical marker condition" scope.
- **A dedicated `SentFlyingEvent` model** — rejected for v1: over-generalizes ahead of a
  second consumer; the non-stackable marker's single-field carrier is honest and
  sufficient today.
- **Bypassing armor/resistance/interpose on the unanswered-impact debit ("full harshness"
  as "unmitigated")** — rejected: "full harshness" means the computed impact amount is
  applied at its full value with no further downgrade, not that it skips the standard
  damage pipeline every other combat hit goes through.

> Status: accepted · Source: issue #2638 / lore `design/2026-07-22-vow-transcripts-batch-3.md` (Transcript 1 R4) / ADR-0118 / ADR-0156
