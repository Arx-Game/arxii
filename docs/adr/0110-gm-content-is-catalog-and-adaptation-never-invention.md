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

## Addendum: the quick-challenge path is built (#2865)

The "long-term direction" the #2857 addendum named is now the code path.
`PlaceChallengeAction` (`place_challenge`, JUNIOR-gated, telnet
`setsituation challenge <template>=<target name>`) places one authored
`ChallengeTemplate` against a thing the GM names, minting a standalone
`ChallengeInstance` with no `SituationInstance` wrapper. The JUNIOR funnel
therefore no longer opens onto an empty room.

Three alternatives were rejected. **Inline mini-situation assembly** — composing a
challenge, an approach and a consequence pool live — is precisely the invention
this ADR gates, so a "lightweight" surface that allowed it would reopen the hole
the gate exists to close. **A family of one-challenge `SituationTemplate`s** would
have needed no new code but forces every impromptu beat to be pre-authored as a
situation row for no mechanical gain. **Gating the band shift by GM level** was
rejected because the shift is already bounded to one band and carries a stated
reason on the row; a second trust axis on top of the placement gate buys nothing.

What the quick path may adapt is unchanged from this ADR's core rule: exactly one
band, with a required reason, stored on the instance
(`ChallengeInstance.severity_adjustment` / `adjustment_reason`, both DB-constrained)
so the number resolution rolls against and the number the audit trail shows can
never disagree. Everything else — which approaches are offered, what consequences
follow, whether the challenge is visible at all — stays the authored template's.

The same PR registered the situation and `gm.*` catalog models in
`CONTENT_MODELS`. That is the other half of "build the catalog": a catalog that
cannot be exported to the lore repo is per-server database state, and every fresh
install starts with a dead JUNIOR tier no matter how good the gating is.

> Status: accepted · Source: issue #2865 (spec approved 2026-08-01)
