# Crafting, Fashion & Economy

## Built (2026-07-07, #2066 — the market)

- Two-tier commerce shipped: capital **market squares** (NPC material/
  reagent/necessity stock as pure sinks; PC stalls of **unfinished wares** —
  real crafted instances the buyer names and describes via a one-shot
  finishing pass) and **crafter shops** (standing craft-as-service offers:
  the buyer runs the attempt with the CRAFTER's skill at their shop, fee up
  front — Arx 1's real loop made consensual). Dual provenance: "Crafted by
  X, Designed by Y".
- Surfaces: web `/market` center + shop directory, telnet `market`
  namespace, 6 REGISTRY actions, org-hosted stall cuts feeding treasuries
  (#1884 stream), PLACEHOLDER seeds (cluster `market`).
- Design tenets recorded: distributed RP hubs over one crowded square; the
  description belongs to the player (no generated prose, ever).
- Honest gap: no item-minting crafting flow exists yet (crafting =
  facet/style attachment) — ware stock comes from existing channels until a
  minting journey ships.


**Status:** in-progress
**Depends on:** Items & Equipment, Magic (resonance/facets), Societies, Areas

## Overview
A rich economic layer that encompasses crafting, fashion, player housing, businesses, and domain management. Crafting was extremely popular in Arx 1 and will be central to Arx II. The fashion-to-resonance feedback loop is unique: assembling a wardrobe that complements your magical motif literally makes you more powerful.

## Key Design Points
- **Crafting as hobby, not class:** Crafting is separate from Path identity. Paths represent a character's adventurer calling; crafts are hobbies or side professions. Avoids overlap with combat roles
- **Material acquisition:** Through world interaction (harvesting gameplay loops), economy (buying), mission rewards, and other sources
- **Recipes:** Discovered, learned, or purchased. Gated by crafting skill levels
- **Fashion-resonance loop:** Items have facets that map to character resonances. A character with a spider facet mapped to their predatory nature gets Praedari resonance bonuses. Assembling a wardrobe that's admired by others creates a feedback loop — social perception feeds magical power
- **Player housing:** Players buy/build rooms, decorate them (decorations give room statistics), run stores and businesses from them
- **Holdings:** Large-scale constructions with defensive stats, research labs, room-specific bonuses
- **Businesses and stores:** Player-run economic entities
- **Ships:** Ownable, upgradeable vessels (e.g., a pirate ship that gets equipped, crewed, and taken on missions)
- **Noble domains:** Territories with material generation, exports/imports, economic management
- **Game economy:** Materials, trade, imports/exports — largely player-driven through crafting and domain interaction
- **Economic progression:** Owning and developing assets is another progression axis alongside XP and Path steps

## What Exists

### Generic crafting framework + enchantment/attach economy (Spec D PR2 — #1031) — DONE

The enchant-and-attach flow for facets and styles is fully playable end-to-end.

**What was built:**

- **`CraftingRecipe` framework** (`world.items.crafting`). The old `FacetCraftingConfig`
  singleton was replaced by data-driven per-kind `CraftingRecipe` rows carrying check config,
  AP/anima costs, a default consumption policy, and three related sub-models:
  `CraftingMaterialRequirement` (ingredient requirements), `CraftingSkillCap` (skill-rank →
  quality ceiling ladder), and `CraftingRecipeConsequence` (weighted consequence pool with
  per-row `CostConsumption` override).

- **Material categories (Build 0a) — DONE.** A `MaterialCategory` equivalence class groups
  `ItemTemplate`s (e.g. "Precious Gemstones"), and `CraftingMaterialRequirement` may target a
  category (any member template satisfies it) instead of a single template — xor-enforced in
  the DB, matched through the shared `gather_consumable_pks` seam. This is the *eligibility*
  axis. **Value-denominated requirements** ("a bounty = N value of a tier") and per-stone
  size/value individuation are **Build 0b**, gated on the gemstone-value ladder brainstorm.
  Crafting execution honors category requirements end-to-end; the quote preview is guarded
  (`CategoryRequirementsNotQuotable`) until the quote surface lands.

- **Gem value model (Build 0b, slice 1) — DONE.** Gem *types* are `ItemTemplate` rows + a
  `GemDetails` sidecar (`quality_level` 1–15; tier = `MaterialCategory`; motif reuses
  `tied_resonance`); a cut gem *instance* is an `ItemInstance` + `GemInstanceDetails` carrying
  size/purity/cut `GemGrade`s (multiplier floor 1.0). Worth = `type_base × size × purity × cut`,
  folded into the wired `appraise()`. Design capture + verify-against-code review in the lore repo.

- **Gem adornment (Build 0b, slice 2) — DONE.** `Adornment` links a host `ItemInstance` to an
  embedded gem instance (narration + provenance); `adorn_item()` gates on
  `ItemTemplate.adornment_capacity`, embeds the gem, and adds its worth to the host's `lore_value`
  (so `appraise()` reflects it). `adorned_materials()` is the queryable "materials on this piece"
  seam the magic app reads. Safe craft-time path only.

- **Gem mining engine (Build 0b, slice 4) — DONE.** `roll_gem_haul()` — the pure, deterministic
  haul generator: one mine cycle yields a common-gem **aggregate value** plus, rarely, a few
  **Rare-Find** gem instances (born uncut). Mine quality + minister bonus raise the Rare-Find
  chance and shift every axis roll up; size/purity floored above common on a find. The multiplicative
  axes give the fat "remarkable find" tail for free.

- **Mine accrual (Build 0b, slice 7) — DONE.** `accrue_mine_cycle()` runs one weekly cycle for a
  mine holding: `DomainHolding` gains `mine_quality` + `common_gem_tier`, and the cycle accrues the
  haul into **uncollected** pools on the holding's income stream (`StreamCommonGemPool` for common
  value, `PendingRareFind` for the stones) — the gem analogue of `OrgIncomeStream.uncollected_pool`.
  **Design (Apostate):** gems are *lumped with tax collection* — they ride the same active
  `collect_org_income` dispatch (same band + graft + catastrophe loss) into the house's stock.

- **Mine collection (Build 0b, domain-cron collection) — DONE.** `collect_org_income()` now
  gathers the org's pending gems alongside coin: the same Tax Collection check, outcome band,
  graft, and catastrophe apply to both. Net common value lands in the house's shared
  `OrgGemStock` (`credit_org_gems`); surviving Rare-Find stones ride the same net rate into the
  collector's hands, and a bad collection loses some (catastrophe loses all). The empty-gate
  considers gems too, so a mine that accrued gems but no coin still collects
  (`org_has_pending_gems`). `CollectionResult` grew `gem_value_landed` / `stones_delivered` /
  `stones_lost`. The gem side lives in `world.items.gems.collection` (a lazy import from the
  currency dispatch, keeping currency free of an items dependency at load).
  **Remaining domain-cron sub-slices:** the **crafting draw** (house members craft from the
  collected `OrgGemStock`), the `game_clock` **scheduling**, and the minister seam (#2239).
  Plus: the **cut recipe** (slice 3 PR) + refinements.

- **Handler registry** (`CraftingHandler` ABC + `FacetAttachHandler` / `StyleAttachHandler`).
  New kinds (alchemy, wand-crafting, etc.) plug in by authoring a `CraftingRecipe` row +
  registering a thin handler — no schema change required.

- **Transactional orchestrator** `run_crafting_recipe` (`world.items.crafting.services`).
  Eight-step atomic pipeline: recipe resolve → pre-validate (no wasted rolls) →
  affordability gate → check roll → graded consequence selection → cost consumption per
  consequence policy → consequence effect application → skill-capped quality tier + attach.

- **Graded cost consumption** (`CostConsumption`: NONE / PARTIAL / FULL). Each consequence
  row in the recipe pool declares how ingredients are consumed if that consequence fires.
  PARTIAL spends `ceil(cost × 0.5)` of AP/Anima but all materials in full.

- **Skill-gated quality cap** (`CraftingSkillCap` + `resolve_capped_tier`). The crafter's
  skill rank gates the maximum quality tier regardless of how well the check rolls.

- **Multi-vector cost** (`stage_and_assert_affordable` + `consume_cost`). AP, Anima, and
  material items are all valid cost vectors; affordability is checked atomically before the
  roll so a failing check never silently deducts resources.

- **Shared material helper** (`world.items.services.materials`). `gather_consumable_pks` /
  `consume_pks` are reused by both the crafting cost path and the ritual path
  (`PerformRitualAction`) — no parallel implementation.

- **Domain wrappers** `craft_attach_facet` / `craft_attach_style`
  (`world.items.services.crafting`). Thin consumers of `run_crafting_recipe` that map
  `CraftRunResult` onto the domain-specific `FacetCraftResult` / `StyleCraftResult`.

- **Read-only crafting quote** (`build_crafting_quote`). Returns a `CraftingQuote`
  (costs, affordability, skill-capped max tier, failure risk) with no mutation;
  exposed as `GET /api/items/item-facets/quote/` and `GET /api/items/item-styles/quote/`.

- **Seeded by** `wire_enchanting_crafting()` (FactoryBoy chain doubling as integration-test
  setUp and seed data): Enchanting skill trait + CheckType + FACET_ATTACH + STYLE_ATTACH
  recipes + a cap ladder + a consequence pool.

**Deferred to follow-up issues:**
- ~~Item-creation pipeline (crafted items with stats, facets, fashion properties)~~ — **DONE (#2195).** `CraftingRecipeKind.ITEM_CREATE` + `ItemCreateHandler` mints a new `ItemInstance` from a recipe's `output_item_template`, with player-authored name/description, quality-scaled stats via `CraftingRecipeModifier`, `OwnershipEvent.CREATED` provenance, and physical `ObjectDB` materialization. `run_crafting_recipe` accepts `item_instance=None` for ITEM_CREATE; `build_crafting_quote` resolves by `(kind, output_template)`. `CreateItemAction` (telnet `craft create` + `POST /api/items/crafting/create/`) is the shared seam.
- Telnet crafting action — **DONE (#1866).** `CmdCraft`
  (`src/commands/crafting.py`) drives facet attach/detach + style attach
  through `AttachFacetAction`/`DetachFacetAction`/`AttachStyleAction`
  (distinct from the #1234 `station` command, which manages the station,
  not the craft itself).

### Crafting-station durability and repair economy (#1234) — DONE

A LAB room feature gates and wears down under `run_crafting_recipe` attempts, with a
coppers-only repair economy. Fully playable end-to-end (telnet + web).

**What was built:**

- **`LabStationDetails` model** (`world.items.crafting.models`) — per-Lab durability state,
  OneToOne to `RoomFeatureInstance` (mirrors `SanctumDetails`'s shape); `durability` /
  `max_durability` + `is_broken` property.
- **LAB `RoomFeatureServiceStrategy`** (`world.items.crafting.station`) —
  `handle_lab_progression` installs/upgrades the feature instance and (re)sets the
  station's durability to the new level's max on both install and upgrade.
- **Repair economy** — `repair_station_durability` (`world.items.crafting.station`), a
  coppers-only sink through `currency.services.transfer` (no destination purse, #923);
  cost scales `LAB_REPAIR_COPPER_PER_POINT_PER_LEVEL × level × points_restored`.
- **Propaganda campaigns (#1621, SHIPPED)** — the money→prestige sink: PROPAGANDA
  `ProjectKind` funded via `project/donate`, instant-completing at threshold and firing
  the sponsor's renown award (details/handler in `world.societies.propaganda`; 3
  PLACEHOLDER campaign scales seeded by the `propaganda` cluster; launched via
  `project/launch <tier>=<name>` / `LaunchPropagandaCampaignAction`). Under-funded
  deadline resolutions keep the coin and award nothing.
- **Station gate/wear pipeline** — `CraftingRecipe.requires_station` (default True) gates
  `run_crafting_recipe`: raises `CraftingStationRequired` / `CraftingStationBroken` before
  affordability-staging, then wears the station by 1 durability after the roll,
  unconditionally.
- **`CraftingQuote.station_status`** — read-only station snapshot (`StationStatus`
  dataclass) surfaced by `build_crafting_quote` when `recipe.requires_station`; narrows
  `affordable` to False when the station is missing or broken.
- **Two new Actions** (`actions/definitions/room_features.py`): `StartRoomFeatureProjectAction`
  (`start_room_feature_project`) — generic install/upgrade project starter for any
  PROJECT-mechanism `RoomFeatureKind`; `RepairLabStationAction` (`repair_lab_station`) —
  spends coppers to restore durability.
- **API** — `LabStationViewSet` at `/api/items/lab-stations/`
  (`GET`, `POST .../install/`, `POST .../upgrade/`, `POST <id>/repair/`).
- **Telnet** — `CmdLabStation` (`station`, `src/commands/crafting_station.py`):
  `station`, `station install [level=<n>]`, `station upgrade level=<n>`,
  `station repair points=<n>`.
- **Frontend** — `LabStationStatusCard` wired into `AttachFacetDialog`.

### Physical currency interplay: coin caches, container access policy, consent-gated theft (#1909) — DONE

Ledger money can leave the books and become a real, holdable item — closing the gap between
"money" (an integer on `CharacterPurse`) and "an item in the world" (droppable, giveable,
stowable, and — deliberately, with consequences — stealable). Fully playable end-to-end
(telnet + web).

**What was built:**

- **`Denomination.LOOSE` + `mint_loose_cache`** (`world.currency`) — everyday pocket cash: an
  arbitrary `face_value`, no mint fee (unlike the six fixed grand-coin denominations, which
  carry `MINT_FEE_PCT` as a deliberate sink). `parse_coppers` (`world.currency.constants`)
  parses free-text `"1g 2s 3c"` amounts so telnet's `CmdGive` can auto-detect money and
  branch into `give_coins` instead of a plain item give.
- **Minted money is born physical** — both `mint_instrument` and `mint_loose_cache` call
  `world.items.services.materialize.materialize_item_game_object`, so a freshly minted coin
  is a real `ItemInstance` + `game_object` in the minter's inventory from the moment it
  exists, not a row waiting to be materialized later. `redeem_instrument` (deposit) is the
  fee-free reverse for *any* instrument (loose or grand) — it consumes the physical object
  (`game_object.delete()` CASCADEs the `ItemInstance` row; `OwnershipEvent` provenance rows
  survive via `SET_NULL`, #1025) so a redeemed coin never lingers as a ghost item.
- **Container Access Policy** (`ItemInstance.access_policy`: Open / Friends / Owner Only,
  `world.items`) — governs who may take items *out* of a container with a plain take;
  non-containers ignore it; only the immediate container's policy applies (no chaining up
  nested containers). Owner-only via `flows.service_functions.inventory
  .set_container_policy`.
- **Ownership/policy gate on plain take** (`take_requires_steal`, `flows.service_functions
  .inventory`) — a room item owned by someone else, or a container-item barred by the
  container's policy, raises `OwnedByAnother` / `ContainerAccessDenied` on `pick_up` /
  `take_out`. Sheet-less actors (GM/staff/companion tooling) keep the legacy free-take
  behavior — theft consequence machinery is sheet-anchored and cannot apply to them.
- **Consent-gated Steal** (`flows.service_functions.inventory.steal`) — the deliberate
  bypass: ownership genuinely transfers (`OwnershipEvent(STOLEN)`, never destroyed, #1025)
  and the act births a crime-tagged, concealed Legend deed (`create_solo_deed`,
  `concealed=True` rolls Stealth to shed witnesses, #1824). Availability
  (`steal_permitted`) is target-side only: an NPC's holdings (no active `RosterTenure`) are
  always antagonism-allowed; a player's holdings gate on `world.consent.services
  .consent_blocks_targeting` against a new `theft_category()` (default-deny — victims must
  opt in). This is the Golden Rule in code: no consequence-free trolling, but a sanctioned
  playground exists for players who opt in to the crime-economy fiction.
- **`SocialConsentCategory.default_mode`** (`world.consent`) — the targeting mode used when
  a tenure has set no per-category rule; `EVERYONE` (default) preserves every pre-existing
  category's legacy allow-all behavior, while `theft_category()` opts into `ALLOWLIST`
  (default-deny). The single-tenure decision moved to the public
  `world.consent.services.consent_blocks_targeting` so non-social-action callers (the theft
  gate) don't reach into the dispatch layer.
- **Actions + telnet** — `withdraw_coins` / `deposit_coins` / `give_coins` / `steal` /
  `set_container_policy` (`actions/definitions/currency.py`), `CanStealPrerequisite`.
  Telnet: `withdraw coins <amount>` (via the existing `CmdWithdraw`), `CmdDeposit`
  (`deposit <item>`), `CmdSteal` (`steal <item>` / `steal <item> from <container>`),
  `CmdSecure` (`secure <container>=<open|friends|owner_only>`); `CmdGive` auto-detects money
  via `parse_coppers`.
- **Web** — `ItemInstanceReadSerializer` gained `game_object_id`, `access_policy`,
  `is_currency_instrument`, and `can_steal`; Drop/Give/Put-in/Deposit/Secure/Steal/Withdraw
  are wired through the existing inventory-action dispatch.
- **Journey test** (`world.items.tests.test_theft_journey`) — service-seam end-to-end:
  withdraw → stow in an owner-only chest → steal (permitted only because the victim opted
  in) → deposit, alongside a non-consenting third party's item staying out of reach; ledger
  conservation (purse balances + outstanding instrument face values) holds at every step.
- **Decision record:** [ADR-0091](../adr/0091-theft-is-consent-gated-target-side.md) (target-side
  theft-consent gate + always-antagonism-allowed NPC holdings).

**Deferred (out of scope, per the #1909 spec):** none filed as follow-ups — the spec's
out-of-scope list stands as written on the issue.

## What's Needed for MVP
- Material/resource models — types, sources, quantities, storage. `partial` — the
  **eligibility layer** shipped (Build 0a: `MaterialCategory` + category-targeted crafting
  requirements). Still needed: value-denominated requirements + per-stone size/value
  individuation (Build 0b, gated on the gemstone-value ladder), mine/domain production, and
  the bulk-commodity market/scarcity layer.
- ~~Item creation pipeline — crafted items with stats, facets, and fashion properties~~ — **DONE (#2195)**
- Fashion system — how worn item facets map to resonances, admiration mechanics (outfit
  trickle is live; admiration mechanics remain future)
- Player housing — room purchase/construction, decoration system, room stats from decor
- Store/business system — player-run shops, inventory management, pricing
- Holdings — large constructions with defensive stats, research labs, special bonuses
- Ship system — vessel models, upgrades, crew, integration with missions. `partial` — #1714
  (battle-time-only vehicle) + #1832 (persistent `ShipDetails`: commission/upgrade/repair,
  ship-as-sanctum, combat-bridge materialize) shipped; crew-as-NPCs, sea travel, cargo-as-goods,
  and mission integration remain. See [ships.md](../systems/ships.md).
- Domain management — noble territory models, material generation, imports/exports
- Trade system — player-to-player and NPC trade mechanics
- Economy balancing — currency flow, material scarcity, price stabilization
- Economy UI — shop management, domain overview, housing decoration

## Notes
