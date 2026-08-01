# GM content is catalog + adaptation, never invention

Situations, challenges, encounters, and checks are **pre-built, browsable, adaptable authored
content** — a GM running a live table discovers and applies the fitting catalog row (with
bounded, reason-carrying situational modifiers), never composes new mechanics ad hoc. #2118's
`InvokeCatalogCheckAction` is the concrete instance: a GM may invoke any authored `CheckType` at
a `DifficultyChoice` band and shift it by at most one band with a required reason, but no code
path accepts a free-form stat/skill pair, an integer difficulty, or a consequence-pool
reference — `perform_check` resolves it and `ConsequenceOutcome`/consequence pools are never
selected, composed, or fired from this surface. We rejected a free-form invocation grammar
(stat + skill + difficulty, chosen live) even though it is the more flexible tool: Arx I ran
without this kind of system, so every GM invented checks and stakes freely at the table, and the
result was rulings of non-canonicity between tables and players denied meaningful, consistent
stories. This ADR governs future GM-content surfaces generally, not just checks — the same
catalog-first shape applies to `SetSituationAction` (#1895), `SetTheStageAction` (#1498), and any
GM-facing authoring tool built after it: build the catalog, make it fast to search, and gate
invention itself, not just its consequences.

> Status: accepted · Source: issue #2118 (rev 2 ruling by Tehom, 2026-07-09)

## Addendum: ad-hoc check gate raised to SENIOR (#2857)

The catalog discipline this ADR establishes prevents GMs from inventing
*mechanics* (no free-form stat/skill, no integer difficulty, no consequence-pool
reference). But the Arx I failure mode was broader: GMs inventing *stakes and
outcomes* — asking players to "make a check" with arbitrary consequences narrated
afterward. `InvokeCatalogCheckAction` already prevents consequence-pool
selection/composition, but the GM narrates whatever they want post-roll.

The fix is gating, not mechanics: `InvokeCatalogCheckAction`'s prerequisite was
raised from `IsSceneGMPrerequisite` (any scene GM) to
`MinimumGMLevelPrerequisite(GMLevel.SENIOR)`. Player GMs below SENIOR trust are
funneled to `SetSituationAction`, where checks emerge from authored situations
with pre-set outcomes. The ad-hoc check remains as a staff/senior stopgap for
impromptu moments. The long-term direction is a lightweight "quick challenge"
path within the situation system, so the ad-hoc check becomes unnecessary for
everyone.
