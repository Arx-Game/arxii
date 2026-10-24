# Checks glossary

**CheckType**:
A named, database-defined check (Stealth, Diplomacy, Composure, Penetration) composed of weighted trait contributions and weighted aspect relevances, grouped under a `CheckCategory`. It is the staff-authored "kind of test" that `perform_check` resolves.
_Avoid_: skill check, roll type, test

**CheckRank**:
A lookup table mapping a point total to a discrete rank level by point thresholds (0/10/25/50/80/115/155/200/250 seeded; they widen with rank but are not exponential). Both the roller's points and the target difficulty are converted to ranks with band positions, and the fractional rank difference selects the chart and how far it slides. Shown with its number: Expert (rank 3).
_Avoid_: tier, grade, rank band

**Band position** (#4601):
How far a total sits through its check rank's band, as a share: 40 points is Competent (rank 2), 60% toward Expert (rank 3). 0 at the rank's own threshold; 0 at the top rank. Both the roller's total and the difficulty have one (`world.checks.slide.band_position`), and result text shows it ("Expert (rank 3), 67% toward Master (rank 4)").
_Avoid_: progress, fraction of a rank, partial rank

**Slide** (#4601):
How a check's odds move inside a band. The rank difference is fractional (roller band position minus target band position); the roll uses chart `lo` (the whole part) slid that share of the way toward chart `lo + 1`, over the "at least X" chances of chart `lo`'s own outcomes. An outcome the next chart has and this chart lacks counts as this chart's nearest outcome by success level, so nothing new appears: everything shifts toward the better outcomes the chart already has, and Critical Success (2) first appears at difference 0. `world.checks.slide.slide_chart`; one d100 roll plus a fraction inside the face.
_Avoid_: blend (the owner's first word; "slide" is the term), interpolation, chart mix

**Own standing** (#4551 decision 7, #4601):
A side's check total without modifiers: traits, skills, specialization, level points, path aspect, capabilities, perks, effort, fatigue, strain and soulfray, against the target's difficulty without the modifiers on it. Modifiers are everything else gathered for the roll (conditions, equipment, distinctions, scene, fashion, relationships, favor, caller bonuses) and the defender's conditions in `level_opposition`. `perform_check(..., extra_standing=, target_modifiers=)` carries the split.
_Avoid_: base total, unbuffed total, raw total

**Hopeless pin** (#4601):
The rule that holds a check on the chart its own standing lands on when that chart has no Success (1) (an impossible chart, -7 and -8 today): modifiers only slide the odds within it, up to 100% of its band, never onto another chart. Net penalties still resolve normally onto a lower chart. The preview grades Impossible on own standing, so a buff never changes that label. Outcome guarantees are capped at the chart's best outcome.
_Avoid_: hopeless clamp, impossible lock, cap

**ResultChart**:
A 0–100 outcome table selected by the rank difference between roller and target. After the effective roll is taken it maps the roll to a `CheckOutcome`. Fifteen charts run from -8 to +6; every "at least X" chance is non-decreasing as the difference rises, and charts -7 and -8 have no Success (1) (the impossible zone, listed to the player as Impossible). A difference below -8 resolves to chart -8.
_Avoid_: difficulty table, roll table, success table

**CheckOutcome**:
The named result of a check (Success, Catastrophic Failure) with a numeric `success_level` from -10 to +10. It is the resolved verdict a chart yields for a roll — consumers branch on success_level, not on raw roll numbers (which are never exposed).
_Avoid_: result, degree of success, outcome tier

**Aspect**:
A broad character archetype (Warfare, Subterfuge, Diplomacy, Scholarship) that grants bonuses to matching checks. Players see aspect names as flavor; the weights linking a CheckType to an aspect are staff-only mechanical values, scaled by the character's most recent path and level.
_Avoid_: archetype tag, talent, domain, house aspect (a house's authored choice is a *charter question* and its answer a *facet*, #4532; "aspect" is this check-side archetype only)

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

**Check call** (#3295):
A GM's room-visible request that named target(s) roll a specific authored `CheckType`
at a specific `DifficultyChoice` band — modeled as one `CheckCall` row (the check +
band + scene + calling GM's persona) plus one `CheckCallTarget` row per target
(`status` PENDING/ANSWERED/DECLINED). The GM never rolls anything; each target
answers (one tap, dispatches the bound self-check) or declines (quiet, no
mechanical force) on their own. Distinct from `InvokeCatalogCheckAction`'s ad-hoc
GM invocation (#2118), which rolls immediately against a target the GM picks and
never creates a call/prompt.
_Avoid_: check request, GM check prompt (the row IS the prompt — "prompt" alone
undersells that it's a structured, catalog-bound object with its own targets and
states)

**Check proposal** (#3295):
A player's (or GM's) structured suggestion for a new `CheckType` the catalog is
missing — `name`/`intent`/`suggested_traits_text`/`situation_text`, routed to the
staff inbox as a `CheckProposal` row (`world.player_submissions`,
`SubmissionCategory.CHECK_PROPOSAL`) and never a live catalog write. The catalog-only
ruling's escape valve: when nothing fits, propose instead of inventing a freeform
stat/skill/difficulty combination on the spot. Adoption — staff authoring the real
`CheckType` row — is a separate, manual act; resolving the proposal (adopt/decline
with `review_notes`) never auto-creates it. Distinct from `CatalogSuggestion`
(#2127, `world.gm`) — the GM scenario-catalog's own freeform-text suggestion kind,
which this deliberately does NOT reuse (structured columns, no JSON, and scoped
to any player, not just GMs).
_Avoid_: check request (confusable with "check call" above), catalog suggestion
(that name is already `CatalogSuggestion`, a different model)

**Resolution wheel** (#924, extended #3807 Part B, Part C):
The dramatic-reveal roulette-style wheel pushed to a player's client when a resolved
check warrants theater, built by `check_outcome_faces`/`maybe_emit_resolution_theater`
(`world/checks/theater.py`) and rendered on the frontend as a flat proportional disc.
For a social check its faces are read only from the check's own `ResultChart` bands,
weighted by roll-range width, never from `rollmod` or an outcome guarantee (ADR-0297);
the wheel always lands on the outcome that actually resolved. A consequence-pool draw
(a weighted pool, not a chart) spins by the same shared gate, `should_emit_theater`: the
drawn tier spins when any candidate is ticked `theater` or carries `character_loss`. A
Soulfray stage draw (#4089) reuses this gate and `consequence_pool_faces` with
`min_faces=1` (a lone candidate still spins), builds its faces from the drawn tier's
UNFILTERED effective consequences so a row a non-lethal cast's own filter removed still
shows and is spun past, delivers to the caster only, and on the scene action path is held
and replayed after that action's own wheel(s) (ADR-4089-B).
_Avoid_: prism, roulette prism (the pre-Part-C frontend shape, since replaced),
roulette wheel alone (ambiguous with the older equal-weighted consequence-pool spin)

**Favor (modifier source)**:
`ModifierSourceKind.FAVOR` (#4333): the labelled line an invocation of a being's favor adds
to the check it was declared on, "<being>'s favor (invocation: <outcome>)", worth the
INVOCATION `FavorOutcomeAward` for the invocation check's outcome tier. It changes a result
only when it moves the total across a rank threshold. Shown only in the acting player's
breakdown, never in a room line.
_Avoid_: "pull" (a thread pull's flat bonus), "boon"

**Extra trait term** (#4450, ADR-4450):
An `ExtraTraitTerm(trait, weight)` a caller adds to one roll through `extra_traits=`, on top of the check type's own `CheckTypeTrait` rows. It scores like one more row (value times weight, through the skill conversion table), earns check-based development once per roll, and counts as involved for capability and thread matching. A system uses it to put a skill into a roll without authoring a check type per character and skill.
_Avoid_: bonus skill, injected trait, synthetic check type (the rejected alternative)

**Modifier level** (#4594, ADR-4594-A):
The level a modifier counts at. A technique's buff or debuff takes it from its cast: the
effective power picks a `CastPowerLevel` row and the outcome shifts it by a
`CastOutcomeLevelShift` row; the `ConditionInstance` keeps it as `modifier_level`. It is the
buff's own level, never the bearer's or the target's. A worn item takes it from its quality
(#4628): the `QualityTier.modifier_level` of the best worn instance of its template (the **item
level rows**).
_Avoid_: buff tier, power level (power is the cast's number; the level is what it resolves to),
item tier (the tier is the quality; the level is what it counts at)

**Modifier size** (#4594, ADR-4594-A):
How big a modifier is for its level, from the `ModifierSize` ladder: Minor, Moderate, Large,
Exceptional (placeholder name), Paramount (placeholder name, reached only through a vow's size
step). Authored on `TechniqueAppliedCondition.modifier_size`: a technique that only buffs is
Large, one that also does something else is Minor or Moderate, narrow use is one step higher.
Also authored on `ItemCheckModifier.modifier_size` for a worn item's check bonus (#4628).
_Avoid_: magnitude, strength, small/big buff

**Value table** (#4594, ADR-4594-A):
The `ModifierValue` rows: what a modifier of each size is worth at each level, in its lane's units
(check points for the check lane). Sparse rows read as steps: a level reads the row at the highest
authored level at or below it. The value is a magnitude; the authored modifier keeps its sign.
_Avoid_: buff table, modifier curve

**Level baseline** (#4594):
The `ModifierLevelBaseline` rows: the typical total a character of each level reaches in a lane.
Staff read a value-table row against it, as a share and, on the check lane, as the share of the
rank band that total sits in.
_Avoid_: expected total, par

**Taper** (#4594, ADR-4594-A, #4551 decision 1):
In one roll, each further modifier of the same source kind on the same lane counts less: largest
first, the k-th at `max(ratio^(k-1), floor)` of its value (the owner's light taper: 7/8, never
below 2/3), bonuses and penalties in separate piles. Set by `ModifierTaper` rows; a kind with no
row never tapers. The character's own standing and a vow's step are never tapered, nor the
equipment walk's vow terms (covenant role, covenant level, vow stat scaling), which ride as the
walk contribution's `vow_part` (#4628).
_Avoid_: diminishing returns (too broad; ADR-0158's vow-keyed grouping is a different rule),
stacking penalty, soft cap

**Lane** (#4594, #4551 section 5.5):
One kind of quantity a modifier can change (`ModifierLane`). Only the check lane exists so far;
later lanes (stats, cast power, damage, soak, healing and more) add a choice and rows to the same
tables.
_Avoid_: channel, track
