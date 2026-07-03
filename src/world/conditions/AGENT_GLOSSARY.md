# Conditions glossary

**ConditionTemplate**:
The authored definition of a condition (e.g. Burning, Frozen) — its category, duration and stacking rules, progression flag, removal rules, and combat settings. The reusable blueprint from which active instances are created.
_Avoid_: status definition, effect type, buff/debuff (for the template)

**ConditionInstance**:
A single active condition on a target (character, object, or room), carrying runtime state: current stage, stacks, severity, remaining duration, source, and suppression. The materialized application of a `ConditionTemplate`.
_Avoid_: active status, applied effect, buff (for the runtime row)

**ConditionStage**:
One step in a progressive condition (`ConditionStage`), ordered within its template, with its own rounds-to-next, resist check/difficulty, and severity multiplier. A condition advances stage-by-stage as rounds elapse.
_Avoid_: phase, level, step

**alters_behavior**:
A boolean flag on `ConditionCategory` marking conditions that change how a character BEHAVES (compulsion, charm, fear, rage) rather than only their capabilities or stats. It is the consent gate: a behavior-altering effect on another PC requires that PC's consent; pure capability/stat effects do not. The canonical behavior-altering category is `Control`, seeded with `alters_behavior=True`, and the fury `Berserk` condition belongs to it.
_Avoid_: is_mental, is_control, hostile (the flag is about behavior-change, not harm)

**conceals_from_perception**:
A boolean flag on `ConditionCategory` marking conditions that make the bearer imperceptible to others (invisibility, magical concealment, stealth). Aggregated by `is_concealed()`; `can_perceive()` composes it with per-observer detection state (`ConditionInstance.detected_by`) and co-location. Distinct from `grants_intangibility` — untargetable is not the same as unseen. The OOC player-transparency guarantee this powers is a separate, unconditional mechanism (ADR-0083), not gated by this flag's detection contest.
_Avoid_: is_invisible, is_hidden, is_stealthed (the flag is about perceptibility, not any one source of it)

**DoT**:
Periodic damage dealt by a condition (`ConditionDamageOverTime`: damage type, base damage, scaling, tick timing). Acute DoT ticks per combat/scene round; long-term (chronic) DoT is flagged `is_long_term`, skipped by the per-round tick, and advanced instead by the daily chronic-effect batch with a non-lethal clamp.
_Avoid_: damage tick, bleed, poison (for the general mechanism)

**Capability effect channel**:
The condition effect that adds to or subtracts from a target's capability value (`ConditionCapabilityEffect`: additive integer, floored at zero). It governs what a character CAN do — movement, flight, casting — distinct from check or resistance modifiers.
_Avoid_: ability modifier, stat effect

**Check effect channel**:
The condition effect that modifies check rolls (`ConditionCheckModifier`: per-check-type modifier value, optionally scaling with severity), folded into a check's extra modifiers by the modifier seam.
_Avoid_: roll bonus, skill modifier

**Resist-check gate**:
The apply-time gate (`ConditionTemplate.resist_check_type` / `resist_difficulty`)
that lets a target roll to resist a condition being applied at all, distinct from
the damage-axis `ConditionResistanceModifier`. The target's own check (folded
through the existing check-modifier seam, so a permanent `ConditionCheckModifier`
from a species/gift/item can make resistance effectively total) beats the
difficulty to resist; `resist_check_type=None` (the default) means unconditional
application, unchanged from every pre-existing condition. Mirrors the removal-side
`cure_check_type` gate in shape.
_Avoid_: immunity flag, is_immune, saving throw

**Resistance effect channel**:
The condition effect that modifies damage resistance (`ConditionResistanceModifier`: per-damage-type modifier, null = all types). Resistance is math, not binary immunity — intensity minus resistance gives the net value. Distinct from the **Resist-check gate**, which resists condition *application* via a check, not damage via a flat modifier — both express "math, not boolean" but on different mechanisms.
_Avoid_: armor, immunity, soak

**TreatmentTemplate**:
The authored definition of a treatment — its name, applicable target condition or pending alteration kind, check type, costs (resonance, anima), whether it requires a bond thread, and optional backlash. The reusable blueprint used by `get_treatment_candidates` and `perform_treatment` when a PC treats another PC's condition or pending magical alteration.
_Avoid_: cure template, heal type
