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

**Level points** (#2707, ADR-0166):
`LEVEL_POINTS_PER_LEVEL * character level` (5 points/level) — a guaranteed term summed
into every `perform_check`'s `total_points`, sourced from
`get_character_path_level`. Additive to the aspect bonus, never a replacement for it: a
character whose Path matches the check's authored aspects still gets both. Unlike the
aspect bonus, it never depends on an authored `CheckTypeAspect` existing.
_Avoid_: level bonus, level modifier (both imply optional; level points are unconditional)

**Level opposition** (#2707, ADR-0166):
The PASSIVE half of an opposed check's difficulty, via `level_opposition(check_type, *,
level, character=None)`: `LEVEL_POINTS_PER_LEVEL * level` always, plus — when a
`character` is given — the acting check's aspects scored against the *defender's* Path.
Used when the defender is not spending a check of their own (an authored lock, a ward, a
combat attack against a `CombatOpponent`). Deliberately exclusive with resist increment
(below) — a call site uses one or the other, never both, since resist increment already
carries the defender's level points internally.
_Avoid_: opposed difficulty (too generic — this names the specific level-plus-aspect
helper), passive resistance (that's the general concept; "level opposition" is this
function specifically)

**Resist increment** (#2707, ADR-0166 — updated: now a full rating, not trait points):
The ACTIVE half of an opposed check's difficulty, via `compute_resist_increment
(defender_character, resist_effort_level)`: the defender's full pre-roll rating on the
Composure `CheckType` (trait, specialization, aspect, and capability points, via
`compute_check_rating` — NOT perk points, since `compute_check_rating` takes no
`situation_ctx` and `_situational_perk_check_bonus` short-circuits to 0 without one,
deliberately, to avoid the side-effect perk-firing announcement a difficulty
computation must never trigger) plus the effort-level modifier, clamped >= 0. Before
#2707 this summed only weighted Composure trait points, silently dropping
specialization/aspect/capability points and the defender's level.
Used when the defender IS actively resisting with a check of their own (e.g. a social
action). Deliberately exclusive with level opposition (above).
_Avoid_: resistance rating (use "resist increment" for this specific helper's return
value), Composure score (the CheckType is Composure; the increment is its rating plus
effort, not a raw trait value)

**Perception Check** (#2997):
The single canonical roll for "does this character notice something is off" —
`resolve_perception_check(observer_sheet, *, difficulty, specialization=None)`
(`perception_services.py`), resolving the seeded stat-only "Perception" `CheckType`
(PERCEPTION primary stat) through `perform_check`. Every perception-gated mechanic
(dreamside noticing, an illusion tell, a disguise tell) calls this one seam rather
than minting its own roll or a flat probability. **ADR-0033 boundary:** a passed
check may reveal that something is amiss, never identity — identification stays
clue-driven (PERSONA_LINK), never an automatic roll. Distinct from Search (stat +
Investigation skill, the deliberate-investigation action's own check) and
Identification (intellect + Investigation, the "recognize who's under the mask"
check, `world/seeds/investigation_checks.py`) — both keep their own compositions.
PLACEHOLDER difficulty magnitudes: `perception_constants.py`'s
EASY/STANDARD/HARD. Root cross-app framing: root `AGENT_GLOSSARY_MAP.md`'s
"Perception" section.
_Avoid_: awareness roll, spot check, notice check.

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
