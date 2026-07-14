# ADR-0133: Asset co-ownership is independent per-owner

## Status

Accepted

## Context

Issue #2295 requires voluntary asset sharing — "introduce my asset to my
ally." The existing `NPCAsset.asset_persona` was a strict `OneToOneField`
(private, single-owner). The issue asked for either a multi-holder or
ownership-transfer model.

Four decisions were ratified during brainstorming:

1. **Multi-owner co-ownership** — multiple PCs hold independent NPCAsset
   rows pointing at the same NPC persona.
2. **Independent per-owner lifecycle** — each owner's NPCAsset row has
   its own `status`. Compromising one owner's row does NOT affect
   co-owners. Only NPC death (`transition_assets_for_dead_character`)
   fans out to all co-owners.
3. **Dedicated Action + service** — the introduce action is a direct
   player verb (`IntroduceAssetAction`), not an NPCServiceOffer. The
   offer pipeline's `handler(offer, persona)` contract can't carry a
   target persona.
4. **Coercion block scoped to COERCION-to-COERCION** — `coerce_into_asset`
   only blocks re-coercion (same NPC already under coercion). Voluntary
   co-ownership does not prevent coercion.

## Decision

1. `NPCAsset.asset_persona` changes from `OneToOneField` to `ForeignKey`.
   Multiple NPCAsset rows can point at the same NPC persona.
2. A new `AssetAcquisitionSource.INTRODUCTION` marks co-owned assets.
3. A new `IntroduceAssetAction` (REGISTRY, key `"introduce_asset"`) is
   the player-facing surface. It takes `asset_id` + `ally_persona_id`
   kwargs and calls the `introduce_asset` service.
4. A partial unique constraint
   `unique_active_npcasset_promoter_asset_persona` prevents duplicate
   co-ownership (one active row per promoter + asset_persona).
5. `coerce_into_asset`'s uniqueness check is scoped to
   `acquisition_source=COERCION`.
6. `transition_asset_status` operates per-row (unchanged).
   `transition_assets_for_dead_character` fans out by `asset_persona`
   (unchanged — covers all co-owners on NPC death).

## Consequences

- Co-owners task the same NPC independently (each filters by
  `promoter_persona`).
- Each owner's stakes are independent (ADR-0092 per-player stakes model
  preserved).
- NPC death is the one shared risk: all co-owners lose their asset.
- Coercion remains single-owner per NPC (one COERCION row at a time),
  but voluntary sharing of a coerced asset is allowed.
