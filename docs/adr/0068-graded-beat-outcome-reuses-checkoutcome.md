# Graded beat/encounter outcome reuses CheckOutcome, not a new enum

`BeatCompletion.outcome_tier` (added in #1716) is a nullable FK to `traits.CheckOutcome`
— the same admin-authored, content-driven graded-tier vocabulary already used by
`Consequence.outcome_tier` and `MissionOptionRoute.outcome_tier`. It is not a new
hardcoded Python enum (e.g. a 5-value `OutcomeTier` TextChoices).

This spec's own brainstorming process initially proposed a new enum before an
anti-reinvention verification pass caught the established, twice-proven pattern —
recorded here so the mistake doesn't repeat for a future domain (e.g. intrigue/
negotiation scenes) that needs graded outcomes. `CheckOutcome` rows are
content-team-authored (name + `success_level` -10..+10), letting authors define
exactly the tier vocabulary they want ("Overwhelming Victory", "Marginal Victory",
"Defeat", "Rout", etc.) without a code change per tier.

All three auto-wire sources this spec adds (combat, mission, scene — PR2-PR4)
converge on one shared seam, `record_outcome_tier_completion`
(`world/stories/services/beats.py`), so a future fourth domain adds a caller, not a
fourth parallel implementation.

> Status: accepted · Source: #1716
