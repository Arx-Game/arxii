# ADR-0092: Asset lifecycle transitions via consequence pools

## Status

Accepted

## Context

Issue #1905 (asset gameplay loops) requires that NPCAsset status transitions
(compromise, loss, dismissal) be triggered mechanically — never by GM fiat.
The original #1872 promotion mechanic left `NPCAsset.status` with only `ACTIVE`
and reserved `COMPROMISED`/`LOST`/`DISMISSED` as future enum members.

The key design constraint, stated by the project owner: "We really, really do
not want a GM to ever by fiat just arbitrarily say 'Yeah, your favorite NPC is
dead.' We need to have rules around this. It needs to be based on impartial
checks and consequence pools. It should never come down to GM whim."

Additionally, assets at risk in a scene must be **declared as stakes upfront**
— the player opts in knowing their agent is on the line before the scene
resolves, not surprised by a consequence after.

## Decision

1. **Single trigger mechanism: `ASSET_STATUS` EffectType on `ConsequenceEffect`.**
   A new effect type in the existing `_HANDLER_REGISTRY` pipeline. Any
   consequence pool — from combat resolution, stake resolutions, social scene
   consequences, GM adjudication — can include an `ASSET_STATUS` effect that
   transitions the target character's active assets to a new status. The effect
   fires mechanically through `apply_all_effects` → `transition_asset_status`.

2. **Stakes integration: `ASSET` StakeSubjectKind + `subject_asset` FK.**
   When an asset is at risk in a scene, it is declared as a stake with
   `subject_kind=ASSET`. The player sees the `player_summary` and opts in.
   `StakeResolution.transitions_subject_asset` is a direct world-state writer
   (mirroring `sets_subject_lifecycle`) for guaranteed transitions on column
   resolution. The `consequence_pool` path provides check-gated transitions.

3. **Flow events for downstream reactivity.**
   `ASSET_COMPROMISED`/`ASSET_LOST`/`ASSET_DISMISSED` EventName values are
   emitted post-transition by `transition_asset_status()` so designers can
   author reactive `TriggerDefinition` rows (alert the promoter, spawn a rescue
   mission). These are notification, not a second trigger surface.

4. **Character death auto-transition.**
   A seeded trigger listens for `CHARACTER_KILLED` and calls
   `transition_assets_for_dead_character()`, which finds active assets whose
   underlying Character died and transitions them to `LOST`. This also routes
   through `transition_asset_status` — no hardcoded side-effects.

5. **Legal-transition matrix.**
   Only `COMPROMISED` is recoverable (back to `ACTIVE`). `LOST` and `DISMISSED`
   are terminal. `IllegalAssetTransitionError` is raised on illegal transitions.

## Consequences

- GMs author the *possibility* of asset loss (a consequence pool entry on a
  scene/stake/encounter); the *actuality* depends on the check roll, not GM
  judgment.
- Players know their assets are at risk before the scene resolves (stakes opt-in).
- Designers can build reactive triggers on asset status changes.
- The tasking framework (`ASSET_TASK_INTEL` OfferKind) reuses the existing
  `NPCServiceOffer` pipeline — zero new dispatch infrastructure.
