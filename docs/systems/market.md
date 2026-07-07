# Market (#2066)

Two-tier commerce: **capital market squares** carry the transactional trade
(NPC stock sinks + PC stalls of unfinished wares); **crafter shops** carry
crafting itself (stations + standing craft-as-service offers). Lives in
`world/items/market/` (submodule per ADR-0017). Design tenets: distributed
RP hubs over one crowded square; the description belongs to the player
(`docs/roadmap/design-tenets.md`).

## Models (`world/items/market/models.py`)

- **`MarketSquare`** — one per realm capital, anchored to an Area.
- **`MarketStall`** — cheap/abstract; `owner_persona` null = NPC stall;
  `host_org` + `cut_percent` route a listing cut to an org treasury (#1884
  merchant stream).
- **`StockListing`** — NPC stock: template + authored price, infinite;
  purchases mint an instance and sink the coin.
- **`WareListing`** — a real crafted `ItemInstance` sold *unfinished*
  (generic name/desc; finite stock); `open_style_slot`/`open_facet_slot`
  flag what the buyer may attach.
- **`FinishingPass`** — the buyer's one-shot right to name/describe the
  piece (stamps designer credit).
- **`CraftingServiceOffer`** — crafter, `recipe_kind`
  (`CraftingRecipeKind`), `shop_room`, fee: executes only at the shop.
- **`MarketSale`** — provenance ledger for every transaction.
- `ItemInstance` gains `designer_character_sheet` +
  `designer_persona_display` beside the crafter pair — "Crafted by X,
  Designed by Y" (collapses when equal); render via
  `dual_provenance_line`.

## Services (`world/items/market/services.py`)

`purchase_stock` (sink + mint), `list_ware` (seller must hold + have
crafted it, and it must be unfinished), `purchase_ware` (transfer + pass
mint + host cut), `finish_ware` (consumes pass; player prose supersedes;
designer credit), `set_service_offer`, `run_service_craft` (wraps the real
attachment pipeline `run_crafting_recipe` with the **offering crafter as
skill source**, buyer present at the shop, fee charged up front — Arx 1's
craft-with-a-crafter's-skill loop made consensual and priced).
`MarketServiceError.user_message` on refusals.

**Honest scope note:** the codebase has no item-*minting* crafting flow
(crafting = facet/style attachment). Ware stock therefore comes from
existing channels (crafter-held instances); when a minting journey ships,
listings consume it unchanged.

## Surfaces

- Actions (REGISTRY): `market_buy_stock`, `market_buy_ware`,
  `market_list_ware`, `market_finish_ware`, `market_set_service_offer`,
  `market_service_craft`.
- REST (read-only): `/api/items/market-squares/` (stalls + live listings),
  `/api/items/service-offers/` (shop directory — advertises only; using a
  service means visiting the shop).
- Web: `/market` — `MarketPage` (browse/buy + directory + `FinishWareForm`).
- Telnet: `market` namespace (`market`, `/buy`, `/buyware`, `/list`,
  `/finish`, `/offer`, `/commission`).
- Seeds: cluster `market` — PLACEHOLDER capital square + NPC stock stall.

## Economy invariants

NPC sales are pure sinks (deflationary tenet); PC-to-PC trades move coin
without minting; org-hosted stalls feed treasuries via the audited ledger.
