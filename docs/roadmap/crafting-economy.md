# Crafting, Fashion & Economy

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
- Item-creation pipeline (crafted items with stats, facets, fashion properties) — still future
- Telnet crafting action (attach-facet/attach-style — distinct from the #1234 `station`
  install/upgrade/repair command, which manages the station, not the craft itself)

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

## What's Needed for MVP
- Material/resource models — types, sources, quantities, storage
- Item creation pipeline — crafted items with stats, facets, and fashion properties
- Fashion system — how worn item facets map to resonances, admiration mechanics (outfit
  trickle is live; admiration mechanics remain future)
- Player housing — room purchase/construction, decoration system, room stats from decor
- Store/business system — player-run shops, inventory management, pricing
- Holdings — large constructions with defensive stats, research labs, special bonuses
- Ship system — vessel models, upgrades, crew, integration with missions
- Domain management — noble territory models, material generation, imports/exports
- Trade system — player-to-player and NPC trade mechanics
- Economy balancing — currency flow, material scarcity, price stabilization
- Economy UI — shop management, domain overview, housing decoration

## Notes
