# Impact tier is a story-side review axis

`Story.impact_tier` (`ImpactTier`: TABLE / REGIONAL / WORLD,
`world/stories/constants.py`, default TABLE) is the story-level canon-impact
review axis — how far a story touches the shared world, authored by the story's
Lead GM at pitch time and gated by a staff `CanonReview` before world-touching
content pays.

This is deliberately distinct from the three pre-existing "stakes" vocabularies
named in ADR-0067's disambiguation table (`Beat.risk`, `combat.RiskLevel`,
`StakesLevel`) — `Story.impact_tier` is a *review* axis, not a danger/reward or
access-scope axis. ADR-0067's table is extended to list it as the fourth
vocabulary so the four never conflate.

The gating is **auto-downgrade, never hard-block** (the pillar-7 pattern from
stakes, ADR-0077): an unreviewed WORLD-tier story's staked beats are UNREADY
(`validate_stakes_readiness` adds a canon-review problem → effective risk NONE
via `StakeContractActivation`; the scene still runs, nothing pays) until a
CLEARED `CanonReview` exists. REGIONAL auto-clears for GMs at EXPERIENCED+
(`GMLevelCap.auto_clear_regional`); TABLE is never reviewed. GLOBAL-scope
WORLD-tier story *activation* additionally requires a CLEARED review
(`create_global_progress`) — the one place the gate is a hard block, because a
GLOBAL story moving the metaplot is not auto-downgradable play.

We considered folding this into `StakesLevel` (combat access scope) but that
gates *who may run a scene of a given scale*, not *whether the story's content
has been canon-checked* — a WORLD-scale combat may be perfectly canonical, and
a TABLE story may touch canon in a way that needs review. Keeping the review
axis on `Story` (not `CombatEncounter`) also covers non-combat beats.

> Status: accepted · Source: #2003
