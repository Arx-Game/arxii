# Assets glossary

- **Asset** — a class-1 `Functionary` promoted into a permanently-owned,
  named NPC. Modeled by `NPCAsset`.
- **Promoter persona** — the PC's persona who cultivated the asset
  (`NPCAsset.promoter_persona`).
- **Asset persona** — the promoted NPC's own persona, private to exactly
  one promoter (`NPCAsset.asset_persona`, `OneToOneField`).
- **Role context** — what kind of relationship the asset serves:
  informant, contact, or personal favor (`AssetRoleContext`).
- **GM search scope** (#3561) - `NPCAssetViewSet`'s widened `get_queryset` for
  a non-staff GM: their own promoted assets plus assets promoted by a persona
  whose character sheet participates in a story that GM leads. Backs the
  stakes editor's ASSET subject picker (`?name=` search via `NPCAssetFilter`).
  Never every player's assets - an `NPCAsset` is per-player private content.
- **Cultivate as Asset** — the player-facing name for the promotion
  `NPCServiceOffer`; not a distinct model or endpoint, just an offer label.

_Avoid_: "companion" (that's `world.companions` — a bound beast/creature,
not a promoted human NPC). _Avoid_: calling `NPCAsset.status` a lifecycle
that's implemented — only `ACTIVE` is wired in this PR.
