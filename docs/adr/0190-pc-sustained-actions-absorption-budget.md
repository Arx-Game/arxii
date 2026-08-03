# PC sustained actions extend ADR-0161's pre-armed shape, with a rolled — not ramped — budget

#2705 gives a PC the same multi-round commitment shape ADR-0161 built for a telegraphed NPC
wind-up: winding up a `Technique` (`windup_rounds > 0`) or conducting a `Ritual` under fire
(`RitualCheckConfig.sustained_rounds > 0`) declares a `SustainedAction` — the direct PC-side
mirror of `PendingOpponentAttack` — instead of resolving the same round. This ADR extends
ADR-0161; it does not reopen it.

## Decision

**Wind-ups stay pre-armed, not mid-round interrupts — Concentration is rolled ONCE, at
declaration.** ADR-0161 explicitly rejected a mid-round check inserted into the resolution
loop; that ruling stands unchanged on the PC side. Declaring a winding-up technique or a
sustained ritual rolls `Concentration` a single time via `roll_sustained_absorption_budget`
to fix the commitment's `absorption_budget`; nothing rolls again while the commitment is
pending, and nothing rolls again at maturation. Every landing hit on the sustaining
participant simply adds a downgrade — the same bookkeeping-only shape `_apply_windup
_interception_rider` uses on the NPC side.

**D1 — No damage ramp on the PC side.** A held `SustainedAction` resolves at **full** effect
while `downgrades < absorption_budget`, and fizzles entirely — no partial resolution — at
`downgrades > 0 and downgrades >= absorption_budget`. The `downgrades > 0` guard matters at
the floor: a Critical-Failure roll clamps `absorption_budget` to 0, and without it `0 >= 0`
would fizzle the commitment at maturation even if the participant was never touched. The
approved spec's own test seam is explicit that a budget of 0 breaks on the participant's
**first landing hit**, not on an untouched commitment reaching maturation in total safety —
a hit is required either way. This is a deliberate divergence from the NPC side, not an
oversight: on the NPC side `x(1 - 0.25*downgrades)` (the `damage_scale` ramp) *is* the
gradation, because nothing about a wind-up ever rolls a check — the ramp is the only signal
of "how hurt was this commitment." On the PC side the Concentration roll already supplied
that gradation, priced into the budget itself; layering a ramp on top would grade the same
input twice and shrink a player's big moment after they earned the roll that set its size.
It also keeps the ritual case coherent: "a ritual at 75% effect" has no defined meaning —
`dispatch_ritual` either fires the authored SERVICE/FLOW/CEREMONY payload or it doesn't.

**The budget ladder, and why it's clamped (D3).** `absorption_budget = clamp
(SUSTAINED_BASE_ABSORPTION (2) + CheckResult.success_level, SUSTAINED_MIN_ABSORPTION (0),
SUSTAINED_MAX_ABSORPTION (4))`. The clamp exists because `CheckOutcome.success_level` is an
authored `-10..+10` `SmallIntegerField`, and **no lore fixture authors a `CheckOutcome` row
at all** — every ladder in the codebase is built ad hoc by seeds/factories, ranging from
-1..1 (`world/companions/factories_combat.py`) to -2..3 (`world/seeds/game_content/clash.py`)
to -5..5 (`CheckOutcomeFactory`'s randomised default). Left unclamped, a wide authored chart
would hand out an absurd budget the moment content diverges from whatever range this feature
was designed against. Base 2 puts a clean Success (`success_level=1`) at budget 3 — landing
exactly on ADR-0161's `WINDUP_FIZZLE_DOWNGRADES` — so a competent PC's commitment survives
exactly as many hits as it takes to break an NPC's telegraphed wind-up.

**D2 — sustaining occupies your action, and the constraint makes it structural.** Declaring a
new action is blocked while an earlier round's `SustainedAction` is still pending
(`_validate_no_pending_sustained`, called from `declare_action`). This is not merely
thematic — you cannot hold a ritual together and also swing a sword — it is *required*:
`CombatRoundAction` carries `UniqueConstraint(["participant", "round_number"],
name="unique_action_per_participant_per_round")`, and maturation clones the declaring
action's fields into a brand-new row for the maturation round. If a same-round declaration
were allowed while a commitment was pending, that clone would collide with it. The guard
filters `resolves_round__gte` (not `__gt`): the round lifecycle is DECLARING(R) *then*
`resolve_round(R)`, so a row maturing THIS round is not yet consumed while declaration is
happening — `__gt` let a second action be declared for the maturing participant's own
maturation round, and `_mature_sustained_technique`'s bare `.objects.create()` for that same
`(participant, round_number)` collided with `unique_action_per_participant_per_round`,
raising an uncaught `IntegrityError` that aborted `resolve_round` for the entire encounter
(#2705 adversarial review, Fix 1). The guard excludes the *current* round's own in-progress
TECHNIQUE declaration (re-declaring the same round replaces, never stacks, via
`_sync_sustained_technique_declaration`'s delete-then-recreate) — but never excludes a
same-round RITUAL row that way, because a ritual is declared through
`try_declare_sustained_ritual`, not `declare_action`, so there is no sync step here that
would replace it (Fix 2b) — one cannot conduct a ritual and also swing a sword in the same
round. `_sync_sustained_technique_declaration`'s own delete is likewise scoped to
`sustained_kind=TECHNIQUE` (Fix 2a): before that scoping, declaring anything else the same
round as a sustained ritual silently deleted the ritual's row — components already consumed,
no refund, no narration.

**The ritual-path corollary to D2, found during implementation.** A ritual is invoked
through `PerformRitualAction`, not through `declare_action` — so D2's raise-based guard never
sees a ritual invocation at all. `try_declare_sustained_ritual` therefore checks the same
already-holding condition but **falls through to immediate dispatch instead of raising** when
it's true. Raising here would be wrong: by the point this check runs, `_validate_components`
has already validated and consumed the ritual's components (inside the same
`transaction.atomic()` `PerformRitualAction.execute()` opened), and a broken/blocked
commitment must not un-consume them — components are spent whether the ritual proceeds
immediately or never sustains at all. A ritual cast while a commitment is already pending
simply isn't deferred; it dispatches now, as if `sustained_rounds` were 0.

**The ADR-0007 kwargs restriction on deferred rituals.** A `SustainedAction` is a DB row with
fixed columns. A ritual whose per-cast kwargs vary (e.g. an Imbuing-style `thread=` target)
cannot be deferred, because persisting an arbitrary kwargs dict to replay at maturation would
require a JSON field — which ADR-0007 forbids outright. `try_declare_sustained_ritual`
therefore returns `None` (dispatch immediately, exactly as today) whenever `kwargs` is
non-empty. Rituals authored with `sustained_rounds > 0` are expected to be no-kwargs
SERVICE/FLOW calls for this reason; a ritual that genuinely needs per-cast arguments is not a
candidate for this mechanism.

**The `perform_check_with_modifiers` requirement — worth recording as a trap.** The budget
roll must go through `perform_check_with_modifiers`, never plain `perform_check`. Only the
`_with_modifiers` wrapper calls `collect_check_modifiers`, which folds in
`ConditionCheckModifier` via `condition_contributions`. Twenty-six authored Concentration
modifier rows exist across nine lore fixtures (blinded, stressed, focused, and so on) — they
are the *entire payoff* of rolling this check at all. Using plain `perform_check` would
compile, pass every unit test that doesn't specifically assert a condition's effect, and
silently make all twenty-six rows inert. This is exactly the shape of bug that survives to
production: the next author extending this seam should know to check which check-rolling
helper they're calling before adding a second call site.

## Rejected alternatives

- **A mid-round Concentration check on each landing hit** — rejected for the same reason
  ADR-0161 rejected a mid-round wind-up interrupt: it would insert a new check point into the
  resolution loop, diverging from the pre-armed-declaration shape the whole reactive-defense
  family (ADR-0060, ADR-0118, ADR-0161) shares. One roll at declaration is deliberately the
  entire mechanic.
- **A damage ramp mirroring the NPC side** (partial resolution at partial downgrades) —
  rejected (D1): double-grades a roll that already happened, and has no coherent meaning for
  a ritual's binary dispatch.
- **Raising in `try_declare_sustained_ritual` when a commitment is already pending**, to
  mirror `_validate_no_pending_sustained`'s raise — rejected: it would strand components
  already consumed in the same atomic transaction, turning "can't sustain a second ritual"
  into "your reagents vanished for nothing."
- **An unclamped budget** — rejected (D3): no lore fixture pins the `CheckOutcome` ladder, so
  an unclamped formula is only as safe as the narrowest authored chart happens to be, and
  breaks the moment any other chart is used.

> Status: accepted · Extends ADR-0161 (does not supersede it) · Source: #2705 · Confidence:
> built and wired — `SustainedAction`, `Technique.windup_rounds`,
> `RitualCheckConfig.sustained_rounds`, `roll_sustained_absorption_budget`,
> `_validate_no_pending_sustained`, `_apply_sustained_erosion_rider`,
> `_mature_sustained_actions`, `try_declare_sustained_ritual`, `dispatch_ritual`. Journey-
> proven under the SQLite fast tier (`world/combat/tests/test_sustained_*.py`,
> `world/magic/tests/test_perform_ritual_action_sustained.py`).
