# Items & Equipment System

Items, equipment, inventory, and currency. Provides the data model foundation for
everything characters can own, wear, wield, and interact with.

**Source:** `src/world/items/`
**API Base:** `/api/items/`

---

## Constants (constants.py)

```python
from world.items.constants import (
    BodyRegion,          # HEAD, FACE, NECK, SHOULDERS, TORSO, BACK, WAIST,
                         # LEFT_ARM, RIGHT_ARM, LEFT_HAND, RIGHT_HAND,
                         # LEFT_LEG, RIGHT_LEG, FEET, LEFT_FINGER, RIGHT_FINGER,
                         # LEFT_EAR, RIGHT_EAR
    EquipmentLayer,      # SKIN, UNDER, BASE, OVER, OUTER, ACCESSORY
    OwnershipEventType,  # CREATED, GIVEN, STOLEN, TRANSFERRED, ACTIVATED, CONSUMED
    PROVENANCE_EVENT_TYPES,  # frozenset {GIVEN, STOLEN, TRANSFERRED} — transfer provenance
)
```

---

## Models

### Lookup Tables (SharedMemoryModel - cached)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `QualityTier` | Color-coded quality levels with stat scaling | `name`, `color_hex`, `numeric_min`, `numeric_max`, `stat_multiplier`, `sort_order` |
| `InteractionType` | Extensible item actions (eat, wield, study, etc.) | `name` (internal), `label` (player-facing), `description` |

### Item Archetypes

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `ItemTemplate` | Archetype definition for an item type | `name`, `description`, `weight`, `size`, `value`, `is_active`, container fields, stacking fields, consumable fields, crafting fields, `interactions` (M2M to InteractionType), `minimum_quality_tier` (FK) |
| `TemplateSlot` | Body region + layer an item occupies | `template` (FK), `body_region`, `equipment_layer`, `covers_lower_layers` |
| `TemplateInteraction` | Flavor text for a specific interaction on a template | `template` (FK), `interaction_type` (FK), `flavor_text` |

### Per-Item State

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `ItemInstance` | A specific item in the game world | `template` (FK, PROTECT), `game_object` (OneToOne to ObjectDB), `custom_name`, `custom_description`, `quality_tier` (FK), `quantity`, `charges`, `is_open`, `holder_character_sheet` (FK to CharacterSheet), `crafter_character_sheet` (FK to CharacterSheet), `lore_value`, `destroyed_at` |
| `EquippedItem` | Tracks equipped item at a body slot | `character` (FK to ObjectDB), `item_instance` (FK), `body_region`, `equipment_layer`. Unique on (character, body_region, equipment_layer) |

### Economy & History

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `OwnershipEvent` | Ownership transition ledger (append-only during play; purged alongside non-lore-critical items on cleanup) | `item_instance` (FK, SET_NULL), `event_type`, `from_character_sheet` (FK), `to_character_sheet` (FK), `notes`, `created_at` |
| `CurrencyBalance` | Per-character gold balance | `character` (OneToOne to ObjectDB), `gold` |

---

## API Endpoints

| Endpoint | ViewSet | Notes |
|----------|---------|-------|
| `/api/items/quality-tiers/` | `QualityTierViewSet` | List quality tiers |
| `/api/items/interaction-types/` | `InteractionTypeViewSet` | List interaction types |
| `/api/items/templates/` | `ItemTemplateViewSet` | List/detail with nested slots and interaction bindings |
| `GET /api/items/inventory/` | `ItemInstanceViewSet` | Read-only inventory list; filtered to `.in_play()` |
| `POST /api/items/inventory/<pk>/use/` | `ItemInstanceViewSet` | Use item; owner-or-staff gated; returns `UseItemResult` |

---

## Key Design Decisions

### Single Typeclass
All items use the same Evennia `Object` typeclass. Item behavior is driven entirely by
`ItemTemplate` properties and `InteractionType` bindings, not by typeclass inheritance.
This avoids typeclass proliferation and keeps game logic in Django models.

### Templates + Instances
`ItemTemplate` defines the archetype (iron longsword, silk shirt). `ItemInstance` holds
per-item state (custom name, quality, charges, owner). Instances reference their template
with `on_delete=PROTECT` to prevent accidental archetype deletion.

### Region + Layer Equipment Grid
Equipment slots use a two-dimensional grid: `BodyRegion` (where on the body) x
`EquipmentLayer` (depth from skin to outermost). This allows layered clothing (underwear,
shirt, jacket, cloak all on the torso) and multi-region items (full plate creates
EquippedItem rows for torso, both arms, etc.). The unique constraint
`(character, body_region, equipment_layer)` enforces one item per slot.

### Ownership Ledger
`OwnershipEvent` is append-only during normal play — ownership transitions are
recorded, not overwritten. However, the soft-delete cleanup path (see "Destruction &
soft-delete lifecycle" below) hard-deletes the entire footprint of non-lore-critical
items, **including their ledger rows**. Ledger rows are therefore permanent only for
lore-critical items (those with `lore_value`, facets, or transfer provenance — i.e.
items that have changed hands). Bare throwaway consumables' CREATED/ACTIVATED/CONSUMED
rows are removed alongside the item on purge. This supports investigation mechanics,
theft tracking, and provenance queries for items that matter.

---

## Destruction & soft-delete lifecycle

Items move through three states:

| State | Meaning | How to query |
|-------|---------|--------------|
| **In play** | Active, in the game world | `ItemInstance.objects.in_play()` (`destroyed_at IS NULL`) |
| **Soft-deleted (recoverable)** | Removed from play but row retained | `destroyed_at IS NOT NULL` |
| **Purged** | Row hard-deleted; gone permanently | — (no row) |

### Predicates on ItemInstance

**`differs_from_template`** (property) — `True` if the instance carries any
per-instance data worth preserving: a `custom_name`, `custom_description`, `lore_value`,
non-default `quality_tier`, any attached facets, or any `OwnershipEvent` beyond
`CREATED`. Used by `consume_item_charges` to decide soft-delete vs. hard-delete at
0 charges.

**`is_lore_critical`** (property) — a tighter subset; `True` only if the item must
*never* be auto-purged. Conditions: `lore_value` is nonzero, OR the item has facets,
OR it has transfer provenance (a `GIVEN`, `STOLEN`, or `TRANSFERRED` ownership event
in `PROVENANCE_EVENT_TYPES`). Cosmetic-only data (custom name, quality tier) is not
lore-critical: those items can be purged once the grace period expires.

### Shared deletion helper

`hard_delete_item_instance(item_instance)` in
`world/items/services/usage.py` removes the instance's complete footprint in one
call: it deletes all `OwnershipEvent` rows for the item first (so no ledger row is
left with a null FK), then deletes the `game_object` (whose CASCADE removes the
`ItemInstance` row) or the `ItemInstance` row directly if there is no game object.
This helper is used by both the destruction-at-0-charges path and the time-based
cleanup, so there is no second code path that could leave dangling rows.

### Time-based cleanup of soft-deleted items

**Service:** `purge_expired_soft_deleted_items(*, grace=None)` in
`world/items/services/cleanup.py`

Runs daily as the `items.soft_delete_cleanup` cron task (registered in
`world/items/tasks.py`). On each run it:

1. Computes a cutoff: `now() - grace` (default: `settings.ITEM_SOFT_DELETE_GRACE_DAYS`
   days, configurable via the `ITEM_SOFT_DELETE_GRACE_DAYS` env var, default **30**).
2. Queries all `ItemInstance` rows with `destroyed_at < cutoff` **and**
   `lore_value=0` **and** zero attached facets **and** zero transfer-provenance events
   (GIVEN/STOLEN/TRANSFERRED), excluding PROTECT-referenced rows (Mantle /
   ProjectContribution).
3. Calls `hard_delete_item_instance` for each out-of-world row in its own savepoint,
   returning the count purged.

**In-world safety guard:** a soft-deleted item must never be in the game world. Any
otherwise-eligible row whose `game_object` still has a location (e.g. a half-undelete
that moved the object back into play but left `destroyed_at` set) is **not** purged —
it is logged at WARNING for staff to resolve (clear `destroyed_at` to truly undelete,
or pull it back out of the world). This prevents the cron from deleting a game object
out from under a live room.

Lore-critical items (`is_lore_critical=True`) are never eligible and remain as
soft-deleted rows indefinitely, available for staff recovery.

**Configuration:**

```python
# src/server/conf/settings.py (default)
ITEM_SOFT_DELETE_GRACE_DAYS = env.int("ITEM_SOFT_DELETE_GRACE_DAYS", default=30)
```

Override via `.env`:

```
ITEM_SOFT_DELETE_GRACE_DAYS=14
```

### Usable vs Consumable Items
An item is **usable** iff its template has an `on_use_pool` FK set (`template.on_use_pool_id is not None`).
`ItemTemplate.is_usable` is the canonical property for this predicate; `use_item`, `ItemUsablePrerequisite`,
and `ItemInstanceReadSerializer.get_is_usable` all delegate to it.

**Consumable** items are the *subset* of usable items where `template.is_consumable` is True:
- Each use spends one charge (atomic `select_for_update`).
- At 0 charges, instances with personalised data (custom name/description, non-default quality tier,
  facets, `lore_value`, or provenance) are **soft-deleted** (`destroyed_at` marker); bare
  template-identical throwaways are **hard-deleted** (the `CONSUMED` `OwnershipEvent` row survives
  via `SET_NULL` on the FK).
- `NoChargesRemaining` is raised before effects fire when `charges <= 0`.

**Reusable** usable items (not consumable) apply effects on every use without spending a charge
or ever being destroyed. An `ACTIVATED` `OwnershipEvent` is logged on each use.

The `use_item` service (`world/items/services/usage.py`) dispatches both branches. Effects are
authored as `checks.Consequence` → `ConsequenceEffect` grouped into an `actions.ConsequencePool`
on `ItemTemplate.on_use_pool`; `on_use_check_type` and `on_use_difficulty` gate the optional
skill check. Both consumable and reusable items return a `UseItemResult` dataclass.

### on_use_target_kind — Validated Targeted Use
`ItemTemplate.on_use_target_kind` (nullable `TargetKind` CharField) controls whether the item
requires an external target and, if so, what kind:

| Value | Meaning |
|-------|---------|
| `null` | Self-use only — a supplied target is rejected. |
| `CHARACTER` | Requires a character target in the same room. |
| `ITEM` | Requires an item target that is reachable. |
| `ROOM` | Requires a room target in the same location. |

`PERSONA` and any unhandled `TargetKind` values fail closed.

**Visibility proxy (MVP):** reachability is confirmed via `_is_visible_to` in
`actions/prerequisites.py`, which checks same-location presence (`target.location in
(actor.location, actor)`). This is an MVP placeholder — there is no perception, stealth, or
darkness system. A real visibility system will replace it when built.

### UseItemAction (Action Layer)
`UseItemAction` (`key="use_item"`, `src/actions/definitions/items.py`) is the action-layer entry
point for using items. It converges with equip/unequip on `action.run()`, so both telnet and the
web dispatcher go through the same prerequisites and service call.

- **kwargs:** `item` (held `ItemInstance` object), `target` (optional effect-target, or `None` for
  self-use).
- **Prerequisites (enforced by `run()`):** `HoldsItemPrerequisite`, `ItemUsablePrerequisite`,
  `OnUseTargetPrerequisite` — all checked after enhancements, before `execute()`.
- **execute():** calls `use_item(item_instance=..., user=actor, target=<validated or None>)`.

Telnet: `CmdUse` (`src/commands/evennia_overrides/items.py`), grammar:
`use <item>` / `use <item> on <target>`. Alias: `apply`.

### is_usable Serializer Field
`ItemInstanceReadSerializer` exposes `is_usable` (a `SerializerMethodField`) equal to
`template.on_use_pool_id is not None`. Clients gate the **Use** button on this field; they do not
need to inspect the template directly.

---

## Integration with Capability/Challenge System

Items interact with the capability/action pipeline in two distinct ways:

### Self-Targeted Items (InteractionType)
Eating food, drinking potions, reading scrolls. The target is the user, the intent is
obvious. These are complete actions handled by `InteractionType` + flavor text + service
functions. They don't need the capability pipeline.

### Capability-Granting Items (Capability Pipeline)
Fire wands, lockpicks, grappling hooks. These don't have a standalone "use" action —
"use fire wand" is meaningless without context. Instead, these items are capability
sources. A fire wand grants `fire_generation`. When a character is in a room with a
flammable challenge, "burn barricade (via fire wand)" appears as an available action
because the wand is a capability source matching an Application.

**"Use" InteractionType should NOT exist for capability-granting items.** Those items
express their usefulness through the capabilities they grant, not through a generic
"use" action.

### Properties on Items
Items can have Properties via `ObjectProperty` (attached to the item's `game_object`
ObjectDB FK). A metallic sword is `metallic`, a holy relic is `blessed`. This makes
items both capability sources AND potential targets for challenges (a rust spell targets
`metallic` items).

---

## Integration with Magic / Threads (Spec A)

- **Items as thread anchors** — The `Thread` model in `world.magic` supports an `ITEM`
  anchor kind (`thread.item` FK → `ItemInstance`). Thread-bearing items accrue
  resonance and level independently of their wielder.
- **Ritual components** — `RitualComponentRequirement` FKs to `ItemTemplate` with an
  optional `QualityTier`, declaring what the ritual consumes on cast.

See `docs/systems/magic.md` for the full thread and ritual model lineup.

---

## Crafting Framework (Spec D PR2 / #1031)

Generic check-driven crafting engine living in `src/world/items/crafting/`. The old
`FacetCraftingConfig` singleton was replaced by this data-driven system. New kinds
(alchemy, wand-crafting, etc.) plug in by authoring a recipe row + registering a thin
handler — no schema change required.

### Constants (`crafting/constants.py`)

| Name | Type | Values |
|------|------|--------|
| `CraftingRecipeKind` | TextChoices | `FACET_ATTACH`, `STYLE_ATTACH` |
| `CostConsumption` | TextChoices | `NONE`, `PARTIAL`, `FULL` |
| `PARTIAL_FRACTION` | float | `0.5` (fraction of AP/Anima consumed on PARTIAL outcomes) |

### Models (`crafting/models.py` — registered under the `items` app)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `CraftingRecipe` | Top-level recipe; one per `kind` (unique) | `name`, `kind` (unique FK), `check_type` (FK; null = disabled), `base_difficulty`, `success_level_step`, `min_success_level`, `skill_trait` (FK to Trait, nullable), `action_point_cost`, `anima_cost`, `default_cost_consumption` |
| `CraftingMaterialRequirement` | Ingredient rows for a recipe | `recipe` (FK), `item_template` (FK), `quantity`, `min_quality_tier` (FK, nullable) |
| `CraftingSkillCap` | Maps a skill-rank band to a quality ceiling | `recipe` (FK), `min_skill_value`, `max_quality_tier` (FK); unique on (recipe, min_skill_value) |
| `CraftingRecipeConsequence` | Weighted consequence pool entry per recipe | `recipe` (FK), `consequence` (FK), `weight_override` (nullable), `cost_consumption`; unique on (recipe, consequence) |

`CraftingSkillCap.for_skill(recipe, skill_value)` returns the `max_quality_tier` for
the highest band at or below the crafter's skill rank (or `None` when no rows exist /
skill is below every band).

### Handler Registry (`crafting/registry.py`, `crafting/handlers.py`)

`CraftingHandler` is an ABC with two abstract methods:

- `pre_validate(item_instance, target)` — raise a typed exception before a roll is
  wasted (capacity exceeded, duplicate, etc.)
- `apply(crafter_account, item_instance, target, quality_tier) -> row` — create and
  return the attachment row

Both concrete handlers are registered at module-import time:

| Kind | Handler | pre_validate delegates to | apply delegates to |
|------|---------|--------------------------|-------------------|
| `FACET_ATTACH` | `FacetAttachHandler` | `assert_facet_attachable` | `attach_facet_to_item` |
| `STYLE_ATTACH` | `StyleAttachHandler` | `assert_style_attachable` | `attach_style_to_item` |

`get_handler(kind)` returns the registered handler; `register(kind, handler)` adds one.

### Orchestrator (`crafting/services.py`)

`run_crafting_recipe(*, kind, crafter_account, crafter_character, item_instance, target)`
is the single transactional entry point. Pipeline (all inside one `@transaction.atomic`
block):

1. **Resolve recipe** — `CraftingRecipe.objects.get(kind=kind)`; raise
   `CraftingNotConfigured` if missing or `check_type` is null.
2. **Pre-validate** — `handler.pre_validate(item_instance, target)` before any roll;
   a capacity/duplicate error never wastes a crafting attempt.
3. **Stage affordability** — `stage_and_assert_affordable(recipe, crafter_character,
   crafter_character_sheet)` → `StagedCost`; raises `CraftingCostUnaffordable` on
   first shortfall (AP, Anima, or materials checked in order).
4. **Roll** — `perform_check(crafter_character, recipe.check_type, recipe.base_difficulty)`.
5. **Select consequence** — `select_consequence_from_result` over the recipe's
   `consequence_rows` pool using `WeightedConsequence` (weight override when set,
   otherwise consequence default).
6. **Consume cost** — `consume_cost(crafter_character, staged, consumption)` per the
   selected consequence's `cost_consumption` (or `recipe.default_cost_consumption` when
   the tier has no authored consequence row).
7. **Apply consequence effects** — `apply_resolution(pending, ResolutionContext(character))`.
8. **Resolve quality + attach** — when `check_result.success_level >= recipe.min_success_level`,
   call `resolve_capped_tier(recipe, crafter_character, check_result)` → `QualityTier`,
   then `handler.apply(crafter_account, item_instance, target, tier)`.

Returns a `CraftRunResult(attached, outcome, row, quality_tier, consumed, consequence_label)`.

### Cost Layer (`crafting/cost.py`)

`stage_and_assert_affordable(*, recipe, crafter_character, crafter_character_sheet) -> StagedCost`
checks AP (`ActionPointPool`), Anima (`CharacterAnima`), and materials (via
`gather_consumable_pks`) in sequence; raises `CraftingCostUnaffordable` on first
shortfall.

`consume_cost(*, crafter_character, staged, consumption) -> dict` applies
`CostConsumption` semantics:

- `NONE` — nothing deducted.
- `PARTIAL` — `ceil(cost × PARTIAL_FRACTION)` of AP and Anima; **all** materials
  consumed in full.
- `FULL` — all AP, Anima, and materials consumed.

Returns `{"action_points": n, "anima": n, "materials": k}`.

### Quality Resolution (`crafting/quality.py`)

`resolve_capped_tier(*, recipe, crafter_character, check_result) -> QualityTier`:

1. `compute_quality_score(check_result, step=recipe.success_level_step,
   min_success_level=recipe.min_success_level)` →
   `check_result.total_points + max(0, success_level - min_success_level) * step`.
2. Look up crafter's `skill_trait` rank; find the highest `CraftingSkillCap` band ≤ rank.
3. If a cap exists, clamp score to `cap_tier.numeric_max`.
4. `QualityTier.for_score(score)` → final tier.

### Shared Material Helper (`services/materials.py`)

Used by both crafting (`stage_and_assert_affordable`) and the ritual path
(`PerformRitualAction`):

- `gather_consumable_pks(*, available, requirements) -> list[int]` — validates inventory
  against requirements, returns PKs to delete; raises `InsufficientMaterials` on first
  shortfall.
- `consume_pks(pks) -> None` — deletes `ItemInstance` rows by PK.
- `meets_quality_tier(inst, requirement) -> bool` — True when the instance satisfies
  the requirement's `min_quality_tier` (or when no minimum is set).

### Wrappers (`services/crafting.py`)

`craft_attach_facet(crafter_account, crafter_character, item_instance, facet) -> FacetCraftResult`
and
`craft_attach_style(crafter_account, crafter_character, item_instance, style) -> StyleCraftResult`
are thin domain wrappers over `run_crafting_recipe` that map `CraftRunResult` onto the
domain-specific result dataclasses.

`compute_quality_score(check_result, *, step, min_success_level) -> int` is co-located
here (imported by `crafting/quality.py`).

### Quote Endpoint (`crafting/services.py` + `views.py`)

`build_crafting_quote(*, kind, crafter_character, crafter_character_sheet, target) -> CraftingQuote`
is a read-only cost snapshot — no mutation, no roll. Returns:

- `costs` (`CraftingQuoteCost`): AP, Anima, and per-material requirements with current
  holdings.
- `affordable` (bool): True iff all vectors are satisfied.
- `max_quality_tier`: Skill-capped ceiling tier (None if no cap rows exist).
- `failure_risk`: List of `CraftingQuoteRisk(outcome_name, cost_consumption, label)` from
  the consequence pool.

Exposed as read-only `GET` actions on the facet and style ViewSets:

| Endpoint | Query params | Response |
|----------|-------------|----------|
| `GET /api/items/item-facets/quote/` | `item_instance`, `facet` | `CraftingQuoteSerializer` |
| `GET /api/items/item-styles/quote/` | `item_instance`, `style` | `CraftingQuoteSerializer` |

### Exceptions (`items/exceptions.py`)

| Exception | Raised by |
|-----------|-----------|
| `CraftingNotConfigured` | No recipe for kind, or `check_type` is null |
| `CraftingCostUnaffordable` | AP / Anima / materials insufficient |
| `CraftingStationRequired` | `recipe.requires_station` is True and no active LAB station is installed in the crafter's room |
| `CraftingStationBroken` | `recipe.requires_station` is True and the installed station is at 0 durability |

### Crafting-Station Gate/Wear (#1234)

`CraftingRecipe.requires_station` (BooleanField, default `True`) marks a recipe as
physically bound to a LAB room feature. `run_crafting_recipe` (step 3, before
affordability-staging) resolves the active LAB `RoomFeatureInstance` in the crafter's
room; missing raises `CraftingStationRequired`, 0-durability raises
`CraftingStationBroken`. After the roll (step 6), the resolved station's durability is
decremented by 1, unconditionally — wear happens regardless of outcome.

`LabStationDetails` (`world.items.crafting.models`) holds the per-Lab durability state
(OneToOne to `RoomFeatureInstance`, mirrors `SanctumDetails`'s shape). The LAB
`RoomFeatureServiceStrategy` handler (`world.items.crafting.station.handle_lab_progression`)
installs/upgrades the feature instance and (re)sets durability to the new level's max on
both install and upgrade — an upgrade project is a refurbishment, not just a bigger cap on
old wear. `repair_station_durability` (same module) restores durability for coppers via
`currency.services.transfer` (sink — no destination purse, #923); cost is
`LAB_REPAIR_COPPER_PER_POINT_PER_LEVEL × level × points_restored`.

`build_crafting_quote` surfaces a read-only `StationStatus` snapshot on
`CraftingQuote.station_status` when `recipe.requires_station` is True, narrowing
`affordable` to False when the station is missing or broken.

**Actions** (`actions/definitions/room_features.py`): `StartRoomFeatureProjectAction`
(key `start_room_feature_project`) — generic install/upgrade project starter for any
PROJECT-mechanism `RoomFeatureKind` (LAB, Command Center, future kinds);
`RepairLabStationAction` (key `repair_lab_station`) — spends coppers to restore a Lab
station's durability. Both REGISTRY, `target_type=SELF`.

**API endpoints** (`LabStationViewSet`, `world.items.views_station`):

| Endpoint | Notes |
|----------|-------|
| `GET /api/items/lab-stations/` | List/detail `LabStationDetails` rows |
| `POST /api/items/lab-stations/install/` | Dispatches `StartRoomFeatureProjectAction` |
| `POST /api/items/lab-stations/upgrade/` | Dispatches `StartRoomFeatureProjectAction` |
| `POST /api/items/lab-stations/<feature_instance_id>/repair/` | Dispatches `RepairLabStationAction` |

Telnet: `CmdLabStation` (`station`, `src/commands/crafting_station.py`) — `station`
(status hub), `station install [level=<n>]`, `station upgrade level=<n>`,
`station repair points=<n>`.

---

## What's Not Yet Built

- **ItemCapabilityGrant model** — links items to capabilities (parallel to TechniqueCapabilityGrant)
- **Equipment source collector** — `_get_equipment_sources()` for `get_capability_sources_for_character()`
- **Unified action aggregation** — frontend layer merging challenge actions, item interactions, and basic actions
- **Real perception/visibility system** — `_is_visible_to` in `prerequisites.py` is a same-location
  MVP proxy; perception, stealth, and darkness mechanics will replace it
- **Time-based cleanup** — cron purge of soft-deleted, non-lore-critical item instances
