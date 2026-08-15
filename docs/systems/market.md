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
  `shopkeeper_persona` (#2995) names a *notable*, persona-bearing NPC
  fronting the stall's stock as a functionary service — mutually exclusive
  with `owner_persona` (a PC stall has no NPC opinion to consult); `host_org`
  + `cut_percent` route a listing cut to an org treasury (#1884 merchant
  stream).
- **`StockListing`** — NPC stock: template + authored price, infinite;
  purchases mint an instance and sink the coin. `min_regard` (#2995,
  nullable) reserves the listing above the global refusal floor — requires
  the stall to have a `shopkeeper_persona`.
- **`WareListing`** — a real crafted `ItemInstance` sold *unfinished*
  (generic name/desc; finite stock); `open_style_slot`/`open_facet_slot`
  flag what the buyer may attach.
- **`FinishingPass`** — the buyer's one-shot right to name/describe the
  piece (stamps designer credit).
- **`CraftingServiceOffer`** — crafter, `recipe_kind`
  (`CraftingRecipeKind`), `shop_room`, fee: executes only at the shop.
  `min_regard` (#2995, nullable) is the same reserved-access gate, a no-op
  when `crafter_persona` is a PC (`NpcRegard` never holds a PC's opinion,
  ADR-0085).
- **`MarketSale`** — provenance ledger for every transaction; `price` records
  what was actually charged, post regard adjustment.
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
`MarketServiceError.user_message` on refusals. `purchase_stock`/
`run_service_craft` return `(result, charged_price)` — the amount actually
charged, which the calling action reports to the player.

## Standing-based service gating (#2995)

A shop run by a persona-bearing NPC (a stall's `shopkeeper_persona`, or a
`CraftingServiceOffer`'s `crafter_persona`) reads `NpcRegard` (#1717) at
purchase time — this is a functionary **service** the NPC extends, not a
static shop window: their opinion of the buyer shifts the price, can gate
reserved stock, and past a hostile floor refuses service outright. "The
world remembers you," wired at the one seam the gap issue called out.
Scoped to persona-bearing NPCs only — `NpcRegard.holder_persona` requires a
real `Persona` (class-2 Standing / class-3-4 Story NPC, ADR-0070); a class-1
`Functionary` (room-placed, personaless — e.g. the permit clerk) has no
opinion to consult, so it's out of scope for this pass. `WareListing`
(a PC's own unfinished-ware stall) is never gated — `NpcRegard` never holds
a PC's opinion (ADR-0085).

Mechanics (`world/items/market/constants.py`, PLACEHOLDER tuning):

- `REGARD_REFUSAL_FLOOR = -500` — at or below this, the seller refuses
  service outright, any listing/offer, authored `min_regard` or not.
- `REGARD_PRICE_BANDS` — ascending `(regard_floor, price_multiplier_percent)`
  tuples walked highest-met-floor-wins (mirrors
  `npc_services.offer_policy._band_count`); `_regard_adjusted_price` applies
  the matched percent to the base price/fee.
- `StockListing.min_regard` / `CraftingServiceOffer.min_regard` — an
  optional per-row gate above the refusal floor, for reserved-stock flavor.

Services: `_shopkeeper_regard` (0 with no shopkeeper or a PC crafter —
`NpcRegard` never has a PC holder), `_regard_adjusted_price`,
`_check_regard_gate` (raises `MarketServiceError` on refusal-floor or
`min_regard` breach). `purchase_stock`/`run_service_craft` call the gate
before charging and use the adjusted price for both the charge and the
`MarketSale.price` ledger row.

Browse (Decision 4 — no personalized price on the read side): the shop
directory (`ServiceOfferViewSet`) and stall stock
(`MarketStallSerializer.get_stock_listings`) show the *base authored*
price/fee only, but for a resolvable viewer hide any row that fails
`_regard_gate_passes` — the exact same predicate the purchase-time gate
checks (refusal floor **and** any authored `min_regard`), resolved via the
viewer's roster tenure. A buyer at or below the refusal floor never sees
even an ungated row at that shopkeeper/crafter — they'd bounce off the same
floor at purchase, so browse and purchase never disagree. An unresolvable
viewer (no roster tenure) can't have regard evaluated at all, so only
`min_regard`-authored rows are hidden as a conservative default; the floor
never applies without a real persona to check it against. The
regard-adjusted price is revealed at purchase-attempt time, in the action's
success message.

**Honest scope note:** item-*minting* crafting (`ITEM_CREATE`) is a real, wired
flow — `craft_create_item` (`world/items/services/crafting.py`) delegates to
`run_crafting_recipe` and backs a real action (#2211/#2881). What's still
gapped is *production data*: `ITEM_CREATE` recipes are lore-authored content
(`CONTENT_MODELS`, #3006) with none authored yet, so a fresh deploy mints
nothing until the lore repo ships example recipes. Ware stock in this market
still comes from existing channels (crafter-held instances) in the meantime;
once ITEM_CREATE recipes are authored, listings can consume minted stock
unchanged.

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

## The Fence (#2862, ADR-0185)

The game's first **sell-to-NPC** path — the market is otherwise buy-only, and
`ItemTemplate.value` had no consumer at all before this. A stall whose
`stall_kind` is `FENCE` buys anything with a template value at `FENCE_RATE_PCT`
(PLACEHOLDER 40%), paid as a coin **mint** (the inverse of the purchase sink),
and asks no questions about provenance — that is what a fence is for.

The price of dealing dirt is heat. `sell_to_fence` mints the previously-dormant
`contraband` CrimeKind for vice (any template whose on-use pool carries an
`INTOXICATE` effect) and `smuggling` for hot-provenance goods, both weighted by
the winning `AreaLaw` at the stall's area — so neighborhood law posture, and
eventually turf control, decides how dangerous a given deal is. Fenced goods
leave the world: the fence is where hot trails go cold (reclamation of
already-fenced items is a noted deferral).

Surfaces: `market_sell_fence` action, telnet `market/fence <item>`, and
`MarketStallAdmin` (staff place a fence by setting `stall_kind`).
