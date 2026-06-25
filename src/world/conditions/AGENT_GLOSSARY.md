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
A boolean flag on `ConditionCategory` marking conditions that change how a character BEHAVES (compulsion, charm, fear) rather than only their capabilities or stats. It is the consent gate: a behavior-altering effect on another PC requires that PC's consent; pure capability/stat effects do not.
_Avoid_: is_mental, is_control, hostile (the flag is about behavior-change, not harm)

**DoT**:
Periodic damage dealt by a condition (`ConditionDamageOverTime`: damage type, base damage, scaling, tick timing). Acute DoT ticks per combat/scene round; long-term (chronic) DoT is flagged `is_long_term`, skipped by the per-round tick, and advanced instead by the daily chronic-effect batch with a non-lethal clamp.
_Avoid_: damage tick, bleed, poison (for the general mechanism)

**Capability effect channel**:
The condition effect that adds to or subtracts from a target's capability value (`ConditionCapabilityEffect`: additive integer, floored at zero). It governs what a character CAN do — movement, flight, casting — distinct from check or resistance modifiers.
_Avoid_: ability modifier, stat effect

**Check effect channel**:
The condition effect that modifies check rolls (`ConditionCheckModifier`: per-check-type modifier value, optionally scaling with severity), folded into a check's extra modifiers by the modifier seam.
_Avoid_: roll bonus, skill modifier

**Resistance effect channel**:
The condition effect that modifies damage resistance (`ConditionResistanceModifier`: per-damage-type modifier, null = all types). Resistance is math, not binary immunity — intensity minus resistance gives the net value.
_Avoid_: armor, immunity, soak
