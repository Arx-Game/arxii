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
Periodic damage dealt by a condition (`ConditionDamageOverTime`: damage type, base damage, scaling, tick timing). Acute DoT ticks per combat/scene round; long-term (chronic) DoT is flagged `is_long_term`, skipped by the per-round tick, and advanced instead by the daily chronic-effect batch with a non-lethal clamp. `tick_timing` defaults to `END_OF_ROUND` (the convention — shieldable by Succor, ticks in combat and scene rounds); `START_OF_ROUND` is a deliberate, guarded opt-in for unpreventable top-of-round damage that is intentionally un-shieldable and currently inert in non-combat scene rounds (#1762 — see `docs/systems/conditions.md`).
_Avoid_: damage tick, bleed, poison (for the general mechanism)

**Capability effect channel**:
The condition effect that adds to or subtracts from a target's capability value (`ConditionCapabilityEffect`: additive integer, floored at zero, plus `scales_with_severity` — honoured by all three value-aggregating readers as of #2708, ADR-0169). It governs what a character CAN do — movement, flight, casting — distinct from check or resistance modifiers.
_Avoid_: ability modifier, stat effect

**Agency oracle** (`get_effective_capability_value`; note `get_all_capability_values` is NOT part of it —
that bulk dict feeds the availability oracle's condition-source enumeration and deliberately excludes
technique grants):
The "can this character do X right now" answer — innate baseline + `CharacterModifier` contributions
(distinctions/species/equipment) + condition contributions + the best (max) known-technique grant, floored
at zero. Consumed by requirement/gate checks (`technique_performable`, mission `challenge_options_for_character`,
positioning/battle movement gates, predicates, vitals awareness). Distinct from the **availability oracle**
(`get_capability_sources_for_character`, `world.mechanics.services`), which enumerates every *source* of a
capability (including prerequisite-gated `TechniqueCapabilityGrant` rows) for "what could grant this."
**One-oracle merge (#2504):** the agency oracle now folds in known-technique grants too — via
`_technique_capability_values`, restricted to `prerequisite__isnull=True` grants only (a source-level
prerequisite is target-contextual, so it stays availability-only) — folding multiple techniques' grants for
the same capability as MAX, never a sum (ADR-0034 individuation; see ADR-0144). `TraitCapabilityDerivation`
deliberately does NOT fold into the agency oracle — that asymmetry is intentional (availability-only), not
an oversight.
**Capability magnitude curve (#2708, ADR-0169):** `get_effective_capability_value` gained an optional
keyword-only `action_ctx: PullActionContext | None` param (~13 pre-existing call sites unaffected by the
`None` default). When supplied, it flows into `_technique_capability_values`'s power derivation, letting more
thread kinds demonstrate real activation (via `magic`'s **Ambient Activation** — see that app's glossary) for
the power figure that curves each `TechniqueCapabilityGrant`. Omitted, an ambient default is built from the
character's current room alone — `TRAIT`-kind threads stay dark under that default (no way to know which
trait, if any, is in play from a bare read). Full detail: `docs/systems/conditions.md`'s "Capability
magnitude curve" section.
_Avoid_: "the capability system" (there are two oracles, not one; name which)

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

**Damage interaction**:
An authored `ConditionDamageInteraction` row that fires when a conditioned target takes a specific damage type — amplifying (`damage_modifier_percent` > 0), dampening (< 0), consuming (`removes_condition=True`), or transforming (`applies_condition` set) the condition. Wired into the combat damage path after all soak/resistance/armor (#2018). Narration fires only on transitions (removal/transform), not on every-hit modifiers — a pure damage modifier is silent math.
_Avoid_: elemental reaction, status effect combo (for the damage-axis interaction)

**capability ladder**:
The shared 0-to-open-ended scale every `CapabilityType.innate_baseline` and `ConditionCapabilityEffect.value` is authored on (ADR-0164): 0 blocked, 1-3 impaired, 5 unimpaired mortal, 8-12 gifted, 25+ greater supernatural, 100+ mythic — deliberately uncapped above, so a high enough value lets a being do what is impossible for a mortal. Blocking is emergent from magnitude, never a flag: a mundane block (-20) stops mortal and gifted but lets a greater supernatural through, a potent block (-100) beats everything below mythic, and an absolute block (-1000) is reserved for mythic-defeating effects. The **agency oracle** and the check-roll capability contribution (`_capability_point_allocation`, `world.checks.services`) both read values on this one ladder.
_Avoid_: capability percentage, capability boolean (there is no percentage scale and no blocks flag — magnitude on the ladder is the only mechanism)

**awareness** (CapabilityType):
The foundational passive sense-gate every character has (`FoundationalCapability.AWARENESS`, `world/conditions/constants.py`) — required by ~all techniques, zeroed by Unconscious via a potent-block `ConditionCapabilityEffect`. Its `innate_baseline` is authored content, not a code constant: ADR-0164 intends 5 (the capability ladder's unimpaired-mortal anchor) once the content row is rescaled, but most environments still carry the pre-rescale `innate_baseline=1` — see `docs/systems/conditions.md`'s "Capability value ladder" section. Distinct from **perception** (below): awareness is "can you sense anything at all," not "how well." See ADR-0143 for the canonical capability vocabulary this belongs to.
_Avoid_: using "awareness" and "perception" interchangeably — they are separate `CapabilityType` rows with different baselines and different roles.

**perception** (CapabilityType):
The active, supernormal-sensing capability from the affordance matrix (`docs/architecture/capability-challenge-content.md`) — `innate_baseline=0` (granted by techniques/gifts, not innate), used for Application eligibility (e.g. Scout, Detect, Analyze, Spot) rather than as a baseline sense-gate. A character can have full `awareness` (conscious, sensing normally) with zero `perception` (no supernormal detection). See ADR-0143.
_Avoid_: awareness, sense, detection (as a synonym for the granted capability specifically)
