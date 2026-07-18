# Checks glossary

**CheckType**:
A named, database-defined check (Stealth, Diplomacy, Composure, Penetration) composed of weighted trait contributions and weighted aspect relevances, grouped under a `CheckCategory`. It is the staff-authored "kind of test" that `perform_check` resolves.
_Avoid_: skill check, roll type, test

**CheckRank**:
A lookup table mapping a point total to a discrete rank level via exponential thresholds. Both the roller's points and the target difficulty are converted to ranks, and the rank difference selects which result chart applies.
_Avoid_: tier, grade, rank band

**ResultChart**:
A 0–100 outcome table selected by the rank difference between roller and target. After the effective roll is taken it maps the roll to a `CheckOutcome`.
_Avoid_: difficulty table, roll table, success table

**CheckOutcome**:
The named result of a check (Success, Catastrophic Failure) with a numeric `success_level` from -10 to +10. It is the resolved verdict a chart yields for a roll — consumers branch on success_level, not on raw roll numbers (which are never exposed).
_Avoid_: result, degree of success, outcome tier

**Aspect**:
A broad character archetype (Warfare, Subterfuge, Diplomacy, Scholarship) that grants bonuses to matching checks. Players see aspect names as flavor; the weights linking a CheckType to an aspect are staff-only mechanical values, scaled by the character's most recent path and level.
_Avoid_: archetype tag, talent, domain

**Composure**:
A seeded social CheckType — resisting social pressure through force of will (willpower-weighted) — resolved when a defender actively resists a social action. Distinct from the Composure Stat (the Social-category trait it draws on).
_Avoid_: willpower check, resolve, resistance (for the named CheckType)

**rollmod**:
A flat per-character roll modifier summed from the character sheet's and the controlling account's `rollmod` values, added to the d100 before clamping to 1–100. A staff/debug lever, returning zero when the relations are absent.
_Avoid_: luck, roll bonus, fudge

**CheckTypeCapabilityModifier** (#2505):
A curated, staff-authored `(check_type, capability, weight)` row — the only path by which a
character's `conditions.CapabilityType` value reaches a check's point total. No row means the
capability oracle is never even called for that check (curated gate, not a zero-weight default).
Contribution is `weight * effective_capability_value`, summed across a check's rows and truncated
toward zero once via `_capability_point_allocation`, shared by the roll path
(`_calculate_capability_points`) and the provenance path (`_capability_contributions` in
`collect_check_modifiers`) so the two can never drift apart. Author at most one channel per
condition/check pair — see `docs/systems/checks.md`'s authoring guardrail — to avoid a condition
double-counting through both a direct `ConditionCheckModifier` and an indirect
`ConditionCapabilityEffect` routed through a weighted capability.
_Avoid_: capability bonus, capability check link, inferred capability check
