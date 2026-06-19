# Items & Equipment

**Status:** in-progress
**Depends on:** Magic (facets/resonance), Crafting

## Overview
The item and equipment system handles everything characters can own, wear, wield, and interact with. Items serve double duty: practical combat stats AND magical resonance through fashion facets. What you wear defines both your combat capability and your magical identity.

## Key Design Points
- **Body slot system:** Different items worn on different body parts — standard MUD/Arx 1 style equipment slots
- **Visible equipment:** What's showing on a character is visible to others, feeding into social perception and aura farming
- **Combat stats:** Weapons and armor have mechanical combat properties
- **Fashion facets:** Items carry facets that map to character resonances. The combat value of gear is only partly in stats — the magical resonance complement matters as much or more
- **Item quality:** Crafted items vary in quality based on crafter skill and materials
- **Item descriptions:** Rich text descriptions that contribute to the game's aesthetic feel

## What Exists
- **Evennia ObjectDB:** Base typeclass for objects exists in typeclasses/objects.py
- **Forms app:** HeightBand, Build — physical form descriptors (tangentially related)
- **Items app (`src/world/items/`):** Data model foundation with:
  - `QualityTier` — color-coded quality levels with stat multipliers (lookup table)
  - `InteractionType` — extensible item actions like eat, wield, study (lookup table)
  - `ItemTemplate` — archetype definitions with weight, size, value, container/stacking/crafting properties
  - `TemplateSlot` — body region + equipment layer declarations per template
  - `ItemInstance` — per-item state with custom name/description, quality, charges, owner
  - `TemplateInteraction` — interaction flavor text per template (e.g., what a muffin tastes like)
  - `EquippedItem` — character equipment tracking at body region + layer
  - `OwnershipEvent` — append-only ownership transition ledger
  - `CurrencyBalance` — per-account gold balance
- **Read-only API endpoints** at `/api/items/` for quality tiers, interaction types, and templates
- **Full test suite** covering models, serializers, and API views**

## Spec D PR1 — Facets, Resonance Regen, Covenant Gear Compatibility (DONE)

**Spec:** `docs/architecture/items-fashion-mantles.md`
**Branch:** `spec-d-items-fashion-mantles-design`

What shipped:

- **`ItemFacet` through-model** — links `ItemInstance` ↔ `Facet` with
  `attachment_quality_tier`; unique per (item_instance, facet); capacity gated by
  `ItemTemplate.facet_capacity`
- **`ItemTemplate` new fields** — `facet_capacity` (PositiveSmallIntegerField, default 0)
  and `gear_archetype` (CharField, `GearArchetype` enum choices)
- **Equip/unequip services** — `equip_item(...)` raises `SlotConflict`/`SlotIncompatible`;
  `unequip_item(...)` — both in `world.items.services.equip`
- **Attach/remove facet services** — `attach_facet_to_item(...)` raises
  `FacetAlreadyAttached`/`FacetCapacityExceeded`; `remove_facet_from_item(...)` —
  in `world.items.services.facets`
- **`CharacterEquipmentHandler`** (`character.equipped_items`) — `iter()`,
  `iter_item_facets()`, `item_facets_for(facet)`, `invalidate()`
- **`EquippedItem` + `ItemFacet` ViewSets** — full CRUD at `/api/items/equipped-items/`
  and `/api/items/item-facets/` with owner-or-staff permissions
- **Equipment modifier integration** — `passive_facet_bonuses(sheet, target)` and
  `covenant_role_bonus(sheet, target)` in `world.mechanics.services`; wired into
  `get_modifier_total` via `EQUIPMENT_RELEVANT_CATEGORIES` gate (Spec D §5.2, §5.6)
- **Outfit resonance trickle** — `outfit_daily_trickle_for_character(sheet) -> int`
  issues `ResonanceGrant` rows (OUTFIT_TRICKLE source, `outfit_item_facet` typed FK);
  `resonance_daily_tick()` now wires outfit trickle alongside residence trickle
- **Covenant gear compatibility** — `GearArchetypeCompatibility` model,
  `CharacterCovenantRole`, `CharacterCovenantRoleHandler`, `assign_covenant_role`,
  `end_covenant_role`, `is_gear_compatible` services; read-only API at
  `/api/covenants/gear-compatibilities/` and `/api/covenants/character-roles/`
- **FACET + COVENANT_ROLE `TargetKind` values** on `Thread`, with typed FKs
  `target_facet` and `target_covenant_role`; anchor cap formulas in
  `compute_anchor_cap` (Spec D §6.1, §6.3)
- **Typed exceptions** — `FacetAlreadyAttached`, `FacetCapacityExceeded`, `SlotConflict`,
  `SlotIncompatible` in `world.items.exceptions`; `CovenantRoleNeverHeldError` in
  `world.covenants.exceptions`; `NoMatchingWornFacetItemsError` in `world.magic.exceptions`

## Spec D PR3 — Covenant-Role × Gear Blend Wired End-to-End (DONE, #985)

**Spec:** `docs/architecture/items-fashion-mantles.md` §5.6, §10 PR3

What shipped:

- **`CovenantRoleBonus` model** (`world.covenants`) — authored config: FK
  `covenant_role`, FK `modifier_target`, `bonus_per_level` SmallInt, unique per
  (role, target). Admin-registered. Default authoring empty → no live numeric effect
  until staff author rows.
- **`role_base_bonus_for_target` wired** — reads `CovenantRoleBonus`; returns
  `character_level × bonus_per_level`; no row → 0. Mirrors `covenant_level_bonus`'s
  authored-config lookup pattern.
- **`item_mundane_stat_for_target` wired** — returns `item.effective_weapon_damage`
  for the seeded `weapon_damage` `ModifierTarget` and `item.effective_armor_soak` for
  `armor_soak`; 0 for other targets. No separate `ItemCombatStat` model (#508 put
  stats on `ItemTemplate`/`ItemInstance` directly). Stale `ItemCombatStat` docstring
  removed.
- **Marginal §5.6 blend** — compatible slot: adds `role_bonus` (stacks on top of the
  gear combat already reads); incompatible slot: adds `max(0, role_bonus - gear_stat)`
  (role surplus only). Equivalent outcome to the original spec; avoids double-counting.
- **Combat seams:** `apply_equipped_armor_soak` adds `_covenant_armor_soak_bonus`
  (routes through `get_modifier_total` for the `armor_soak` target); `_weapon_augmented_budget`
  adds `_combat_target_bonus(sheet, WEAPON_DAMAGE_TARGET_NAME)` to technique budget.
  Non-covenant characters and base damage/soak are unchanged.
- **Tests** — `test_covenant_combat_blend.py` (integration: weapon + soak seams +
  non-covenant regression + unseeded-target guard); `test_covenant_role_bonus_gating.py`
  (unit); `test_modifier_total_no_query.py::CovenantRoleAnchorCapQueryBudgetTests`
  (no-query path still passes).

## Spec D PR4 — Mantle System + Fashion Combat Integration (DONE)

**Spec:** `docs/architecture/items-fashion-mantles.md` §4.3, §5.4, §6.2 (issue #512)

What shipped:

- **Mantle models** (`world.items`) — `Mantle` (OneToOne→`ItemInstance`; a specific
  attunable artifact, not a category), `MantleLevelDefinition` (per-level Codex gate via
  `codex_entry_required`), `MantleLevelClearance` (per-character gate-join row)
- **Mantle clearance services** — `record_mantle_clearances(sheet, mantle)` (idempotent;
  records a clearance per level whose required `CharacterCodexKnowledge` is KNOWN, in
  order), `grant_mantle_clearance(...)` (staff override), `get_max_cleared_mantle_level(...)`;
  `CharacterMantleClearanceHandler` (`character.mantle_clearances.max_cleared_level(mantle)`).
  Mission gate deferred to the future Mission spec
- **MANTLE `TargetKind`** on `Thread` with typed FK `target_mantle` (per-kind
  CheckConstraint + partial UniqueConstraint, mirroring FACET/COVENANT_ROLE);
  `weave_thread` gates MANTLE weaves on ≥ level-1 clearance (`MantleNotClearedError`);
  `compute_anchor_cap` MANTLE arm = `max_cleared_level × 10` (Spec D §6.2); wired into
  the thread-weave serializer (resolve + 400 on gate error)
- **Mantle combat bonus** — `passive_mantle_bonuses(sheet, target)` (per-thread tier-0
  FLAT_BONUS pulls, `base × max(1, level)`, no item/quality multipliers — the bonus is
  the attunement itself); the facet/mantle pull-effect lookups unified into
  `_thread_pull_effects_for(..., target_kind=)`
- **Equipment walk surfaced in combat** — `equipment_walk_total(character, target)`
  (facet + covenant-role + mantle) extracted from `get_modifier_total` and surfaced in
  `collect_check_modifiers` (the central check seam combat funnels through), so
  facet/covenant/mantle/fashion now reach combat and every check — previously the walk
  surfaced in no real check. Eager `CharacterModifier` rows counted exactly once (no
  double-count)
- **Scene-derived perceiving society** — `Area.dominant_society` FK +
  `societies_for_scene(scene)` (permissive: all societies sharing the area's realm,
  unless the area names one); the seam takes the **max** `fashion_outfit_bonus` across
  relevant societies; `ModifierSourceKind.FASHION` provenance value. (The engine
  shipped here; the **combat consumers that actually supply `scene=` were wired in
  #750** — see the section below. Until then fashion was always 0 in combat and
  defense bypassed the seam entirely.)
- **Integration test** — craft → wear → combat for a mantle-bearing item, end-to-end
  through the real services (clearance → gated weave → equip → `collect_check_modifiers`)
- **Typed exception** — `MantleNotClearedError` in `world.magic.exceptions`

## Combat passes the scene-derived perceiving society (DONE, #750)

Spec D PR4 built the engine (`societies_for_scene`, `Area.dominant_society`, the
`max`-across-societies fold in `_character_and_equipment_contributions`, and a
`scene=` parameter on `collect_check_modifiers`) but the **combat consumers never
supplied a `scene`**, so the fashion bonus was always 0 in combat and defense
never used the modifier seam at all. #750 closes that consumer-side gap:

- **Every participant combat check derives its perceiving society from scene
  context** — offense, penetration, flee, and environmental checks pass
  `scene=encounter.scene`; the clash contribution passes `scene=clash.encounter.scene`
  (`world/combat/services.py`, `world/combat/clash.py`). No signature/plumbing
  changes — each site reads the scene from its in-scope encounter/clash.
- **Defense now joins the seam (the headline).** `resolve_npc_attack` previously
  rolled the defender's check with **zero modifiers**; it now routes through
  `collect_check_modifiers(participant.character_sheet, check_type,
  scene=participant.encounter.scene)` and feeds `extra_modifiers` into the roll.
  Fashion **and** covenant-role/equipment-walk **and** persistent
  `CharacterModifier`s **and** conditions now all reach defense — so a character
  whose attire matches the perceiving society's vogue is genuinely harder to
  hit/kill (durability from vibe).
- **Capability vs. content:** the bonus is nonzero only where a defensive
  `CheckType` has a scoped `modifier_target` with authored `FashionStyleBonus`
  rows. The wiring ships the capability; an integration fixture
  (`combat/tests/test_defense.py::DefensiveFashionWiringTests`) proves the path
  end-to-end. Broad authoring is seed content.
- **Threads already cut damage post-defense** (`apply_damage_reduction_from_threads`),
  so durability-from-investment now spans threads (damage reduction) +
  fashion/covenant (defensive check bonus).

Follow-ups filed: covenant-role gating whether a character benefits from armor
soak; thread defensive-magnitude tuning.

## Item Interaction Service Functions — Use / Consume Charges (DONE, #509)

**Branch:** `feature-509-item-interaction-service-functions-use-c`

Service layer (+ a REST entry point) for using consumable items — potions, scrolls,
charged-use items. Reuses the wired effect stack end-to-end rather than introducing new
effect or pool primitives: effects are authored as `checks.Consequence` → `ConsequenceEffect`
and grouped into an `actions.ConsequencePool` (the same abstraction combat clashes use).

What landed:

- **Schema (`ItemTemplate`):** `on_use_pool` FK → `actions.ConsequencePool` (null = not usable),
  `on_use_check_type` FK → `checks.CheckType` (null ⇒ deterministic apply; set ⇒ check-gated),
  `on_use_difficulty` (authored difficulty, required iff `on_use_check_type` set; enforced in
  `clean()`). No new through-model — reuses the pool abstraction.
- **Soft-delete (`ItemInstance`):** new `destroyed_at` marker + `differs_from_template` property
  + `objects.in_play()` queryset. At 0 charges, instances carrying per-instance data (custom
  name/description, non-default quality tier, facets, `lore_value`, or provenance) are
  **soft-deleted** (row + history preserved); bare template-identical throwaways are
  hard-deleted (the `CONSUMED` ledger row survives via `OwnershipEvent.item_instance` `SET_NULL`).
- **Service `world/items/services/usage.py`:** `consume_item_charges` (atomic, `select_for_update`
  charge lock, `ACTIVATED`/`CONSUMED` ledger, soft/hard delete) and `use_item` (deterministic via
  `apply_pool_deterministically`, or check-gated via `select_consequence` + `apply_resolution`;
  charge spent regardless of check outcome). Returns a `UseItemResult` dataclass.
- **Typed exceptions:** `ItemNotUsable`, `NoChargesRemaining` (in `world.items.exceptions`).
- **REST:** `POST /api/items/inventory/<pk>/use/` — a `use` action on `ItemInstanceViewSet`,
  owner-or-staff gated, `ItemError` → HTTP 400; list/retrieve filter `.in_play()`.

Deferred follow-ups: use-item *Action* (`actions/definitions/`) converging on `action.run()`
alongside equip/unequip; durability-on-use (#508) integration; quantity/stack consumption;
frontend "use item" UI.

## Time-Based Cleanup of Soft-Deleted Items (DONE, #1025)

**Branch:** `feature-1025-time-based-cleanup-of-soft-deleted-non-l`

Closes the deferred cleanup follow-up from #509: non-lore-critical soft-deleted items are
now automatically hard-purged after a configurable grace period.

What landed:

- **`is_lore_critical` predicate** on `ItemInstance` (`world/items/models.py`) — returns
  `True` if the item must never be auto-purged: `lore_value != 0`, OR has attached facets
  (`ItemFacet` rows), OR has transfer provenance (a GIVEN, STOLEN, or TRANSFERRED
  `OwnershipEvent`). Cosmetic-only data (custom name, quality tier) is deliberately *not*
  lore-critical so throway cosmetics are still eligible for purge.
- **`PROVENANCE_EVENT_TYPES`** frozenset in `world/items/constants.py` — `{GIVEN, STOLEN,
  TRANSFERRED}` — the transfer-event guard shared by the predicate and the cleanup query.
- **`hard_delete_item_instance(item_instance)` shared helper** in
  `world/items/services/usage.py` — convergence of the destruction-at-0-charges path
  (#509) and the cleanup path (#1025). Deletes ledger rows first, then the game object
  (CASCADE) or instance row directly; no dangling FKs possible. Previously, bare-throwaway
  destruction left a `CONSUMED` ledger row with `item_instance=NULL`; that dangling-row
  behavior is now retired for hard-delete paths.
- **`purge_expired_soft_deleted_items(*, grace=None) -> int`** in
  `world/items/services/cleanup.py` — queries `destroyed_at < cutoff AND lore_value=0
  AND facets=0 AND transfer_provenance=0`, calls `hard_delete_item_instance` for each,
  returns the count purged. Wraps everything in `@transaction.atomic`.
- **`ITEM_SOFT_DELETE_GRACE_DAYS`** in `settings.py` — defaults to 30, configurable via
  the `ITEM_SOFT_DELETE_GRACE_DAYS` env var. Passed as `timedelta(days=N)` to the
  cleanup service.
- **`items.soft_delete_cleanup` daily cron task** in `world/items/tasks.py` — registered
  with `world.game_clock.task_registry` via `register_all_tasks()`; runs every 24 hours;
  logs the purge count.
- **Tests** — lore-critical items are retained forever; past-grace non-lore-critical items
  are purged; within-grace items are retained; no-op when nothing eligible; no orphaned
  ledger rows after purge.

## Inventory Service Functions (DONE)

**Branch:** `inventory-service-functions-design`

Action-layer service functions composed on top of the items data layer. The split is
deliberate: `world/items/services/` owns row-level mutations (equip_item / unequip_item /
attach_facet_to_item / remove_facet_from_item — narrow, atomic, no permission logic),
while `flows/service_functions/inventory.py` owns the player-facing actions (pick_up,
drop, give, equip, unequip, put_in, take_out — permission checks via `ItemState`,
`OwnershipEvent` rows on transfers, auto-unequip on drop/give, slot-conflict auto-swap on
equip). The 7 service functions back the `Action` classes in `actions/definitions/items.py`
(plus the refactored Get/Drop/Give in `actions/definitions/movement.py`); telnet commands
and the existing web action dispatcher both call `action.run()`, so the two transports
cannot diverge.

What landed:

- **`InventoryError` typed exception family** in `world.items.exceptions` —
  `PermissionDenied`, `NotEquipped`, `NotInPossession`, `NoDropLocation`, `NotAContainer`,
  `ContainerClosed`, `ContainerFull`, `ItemTooLarge` — each with a `user_message` for safe
  surfacing through the API
- **`ItemState`** flow object state with default-allow `can_take`, `can_drop`, `can_give`,
  `can_equip` permission methods
- **Action-layer service functions** in `flows/service_functions/inventory.py`:
  `pick_up`, `drop`, `give`, `equip`, `unequip`, `put_in`, `take_out` — all wrapped in
  `transaction.atomic`, all delegating row-level mutations to `world.items.services`
- **`OwnershipEvent(GIVEN)`** rows written on `give` so the ownership ledger tracks
  player-to-player transfers (crafting will write its own `OwnershipEvent.CREATED`)
- **Action classes** for equip/unequip/put_in/take_out in `actions/definitions/items.py`,
  plus the existing Get/Drop/Give in `actions/definitions/movement.py` refactored to use
  the new service functions (so they now track ownership and write OwnershipEvent rows)
- **Telnet commands** `wear`, `remove`, `put`, `withdraw` in
  `commands/evennia_overrides/items.py`, registered in `CharacterCmdSet`. The existing
  `get`/`drop`/`give` commands continue to work unchanged
- **`execute_action` WebSocket inputfunc** in `src/server/conf/inputfuncs.py` —
  generic action dispatcher: the React frontend sends
  `{type: "execute_action", action: "<key>", kwargs: {target_id: N, ...}}`,
  the inputfunc resolves `_id`-suffix kwargs to ObjectDB instances and runs the
  registered action against `session.puppet`. Returns the result via the new
  `ACTION_RESULT` WebSocket message type. This is now the canonical mutation
  channel for the React client — REST is read-only
- **Removed the REST POST/DELETE on `/api/items/equipped-items/`** — they were a
  duplicate path that bypassed the action layer's policy (raised `SlotConflict`
  instead of auto-swapping). All inventory mutations now flow through the action
  layer; the ViewSet remains as a read-only list/retrieve endpoint

## Outfits Phase A (DONE)

**Branch:** `outfits-phase-a`

Saved outfits — named groupings of equipped items a character can re-apply in one
action. Phase A is the data layer, action layer, and the wardrobe UI scaffold; it
does not yet include fashion bonuses, modeling, or legendary mechanics (those are
Phases B–D below).

What landed:

- **`Outfit` and `OutfitSlot` models** in `world.items.models` — `Outfit` is owned
  by a `CharacterSheet` (the source-of-truth above personas) and stored in a
  wardrobe `ItemInstance`; unique name per character_sheet; `clean()` validates
  that the wardrobe's template has `is_wardrobe=True`. `OutfitSlot` pins a
  specific `ItemInstance` to a `(BodyRegion, EquipmentLayer)` pair on the outfit.
  Added an `is_wardrobe` flag on `ItemTemplate` to mark items that can store
  outfits
- **Service functions** in `flows.service_functions.outfits`:
  - `apply_outfit(character, outfit_state)` — atomic equip of all slots; uses
    the existing equip auto-swap policy; raises `PermissionDenied` for
    cross-character outfits, `NotReachable` if the wardrobe or any slot's item
    is out of reach
  - `undress(character)` — unequips everything currently worn; idempotent on
    naked characters; items stay in inventory
  - `save_outfit(*, character_sheet, wardrobe, name, description="")` — snapshots
    the character's currently-equipped items into a new Outfit
  - `delete_outfit(outfit)` — removes the outfit definition; items untouched
  - `add_outfit_slot(*, outfit, item_instance, body_region, equipment_layer)` —
    adds or replaces a slot; rejects template-incompatible slots
  - `remove_outfit_slot(*, outfit, body_region, equipment_layer)` — idempotent
- **`OutfitIncomplete` typed exception** for use when an outfit references items
  that no longer exist (cascade-deletes on `OutfitSlot.item_instance` mean the
  slot row vanishes; the exception is reserved for callers that want to surface
  "this outfit has missing pieces" to the user)
- **`OutfitState`** flow object state with `can_apply` (routed through
  `_run_package_hook`) and `is_reachable_by` that delegates to the wrapped
  wardrobe's `ItemState.is_reachable_by` — so behavior packages can intercept
  outfit-apply just like they intercept item operations
- **`ApplyOutfitAction` and `UndressAction`** in `actions/definitions/items.py`
  (registered in the action registry), so both telnet and the web action
  dispatcher route through the same service layer
- **Telnet commands** — `wear outfit <name>` is a new branch on the existing
  `CmdWear`; `undress` is a new command in `commands/evennia_overrides/items.py`,
  registered in `CharacterCmdSet`
- **REST endpoints** at `/api/items/`:
  - `OutfitViewSet` — full CRUD on outfits (owner-or-staff)
  - `OutfitSlotViewSet` — full CRUD on slot pins
  - `ItemInstanceViewSet` — read-only inventory list/retrieve so the wardrobe page
    can paint the inventory grid without a websocket round-trip on first load
- **Frontend wardrobe page** (`frontend/src/inventory/`):
  - `WardrobePage` shell with paper doll, currently-worn list, inventory grid,
    item detail side drawer, and an outfit cards row
  - `OutfitCard` with placeholder regions for future Phase B fashion bonuses,
    Phase C modeling stats, Phase D legendary level / mantle indicator — wired
    but empty so we don't have to retrofit the layout later
  - Save / Edit / Delete outfit dialogs
- **WebSocket plumbing** — new `execute_action` outbound message type and
  `action_result` inbound message type, plus a small action result bus the
  wardrobe page subscribes to so apply/undress feedback surfaces immediately

Explicitly NOT in Phase A: fashion compatibility, fashion bonuses, modeling /
peer judging, outfit legendary level, outfit-bound mantles. Placeholders are in
the UI but no server-side mechanics back them.

## Outfits Phase B — Fashion Style (DONE)

**Branch:** `feature-513-outfits-phase-b-fashionstyle`

Fashion bonuses driven by admin-authored `FashionStyle` objects tied to the current
season/rotation for each Society. The perceiving society supplies the context; there
is no society-blind always-on scalar (no "home society" link exists on characters).

What shipped:

- **`FashionStyle` model** (admin-authored) — `name`, `description`, and an
  `in_vogue_facets` M2M → `magic.Facet`; facets on the style define what's
  currently fashionable. Compatibility is facet-only for MVP; extending to item
  type or gear archetype is a deferred extension point.
- **`FashionStyleBonus` through-model** — maps a `FashionStyle` to a per-`CheckType`
  `mechanics.ModifierTarget` with an authored `weight`. Defines the mechanical payoff
  when a character's outfit is in-vogue.
- **`Society.current_fashion_style` FK** — the per-Society "current fashion" rotation;
  set in Django admin. Changing it updates which facets are in-vogue for that society's
  perception context.
- **`fashion_outfit_bonus(sheet, target, society)` service** — perception-relative;
  mirrors `passive_facet_bonuses`; queries the character's currently equipped item
  facets against the society's `current_fashion_style.in_vogue_facets`. Returns a
  weighted modifier for the given `ModifierTarget`.
- **`get_modifier_total(character, target, *, perceiving_society=...)` integration** —
  society-aware callers (#514 events, #512 combat) pass `perceiving_society`; existing
  society-blind callers are unchanged.
- **Admin** — `FashionStyleAdmin` with `FashionStyleBonus` inline registered;
  `SocietyAdmin` exposes `current_fashion_style`.

Design decisions:

- **Contextual / perception-relative:** the perceiving society is supplied by
  consumers; no always-on fashion scalar is applied globally.
- **Facet-only compatibility for MVP;** item-type/archetype extension is a future
  hook.
- **Follow-up #750 filed:** derive the perceiving society from scene context so
  event/combat callers don't have to thread it manually.

## Outfits Phase C — Modeling at Events (DONE)

**Branch:** `feature-514-outfits-phase-c-modeling-events` (#514)

Players present outfits at events, peers judge them, acclaim feeds personal renown
and an opt-in fashion leaderboard, and — the centerpiece — high performers set the
trends a society considers fashionable, replacing the admin-only
`Society.current_fashion_style` toggle with a player-driven seasonal ceremony.

The loop: **present → society-taste-shaped check → peer judging (dominant weight) →
acclaim → { fashion prestige + leaderboard } + { vogue momentum } → seasonal
trendsetter ceremony → the crowned trendsetter's facets become the society's
in-vogue trend → everyone's `fashion_outfit_bonus` shifts.**

What shipped:

- **`FashionPresentation` model** (`items`) — a character modeling an outfit at an
  `Event`, judged by the event's host society. Records `base_score` (graded check)
  and `acclaim` (peer-weighted final).
- **`Event.host_society` FK** — the society whose taste judges presentations at that
  event (the concrete perceiving-society source for events; #750 still owns the
  general scene/combat derivation).
- **`EndorsementBase` abstract model** — extracted from `PoseEndorsement` /
  `SceneEntryEndorsement`; the new **`PresentationEndorsement`** (peer fashion
  judgment, no resonance) is the third sibling. No parallel implementation.
- **`present_outfit` / `judge_presentation` services** — the presentation runs a
  check whose modifier is `fashion_outfit_bonus` (vs the host society) and whose
  difficulty derives from the society's current taste; peer endorsements then
  dominate the final acclaim. Consent boundary: only characters who present are
  judgeable; no self/alt/duplicate judging.
- **`Persona.prestige_from_fashion`** — a 5th prestige axis (same event-sourced
  recompute pattern as the other four), surfaced on the Renown tab.
- **`FacetVogueMomentum` + trendsetter ceremony** — acclaimed presentations accrue
  per-`(society, facet)` vogue momentum (cron-decayed); a seasonal cron crowns the
  top presenter (`Trendsetter`) and rewrites the society's living `FashionStyle`
  in-vogue facets. Also host/staff-triggerable.
- **`RankingType.FASHION`** — the opt-in fashion leaderboard reuses the existing
  #676 `RankingDisplay` / `ranking_services` / `RankingBoardCard` infra (no parallel
  board), ranking by perceived `prestige_from_fashion`.
- **API + frontend** — present/judge endpoints (`/api/items/fashion-presentations/`,
  `/api/items/fashion-judgements/`) and a `FashionPresentationPanel` mounted in the
  event detail view; the Renown prestige card now shows the Fashion axis.

Design decisions:

- **Peer-weighted hybrid judging:** the check sets a floor; peer endorsements are
  the dominant lever. Difficulty derives from authored society taste, never a
  hardcoded per-call constant.
- **Trend-setting as ceremony:** a *named* trendsetter is crowned each season — the
  high-drama, individualizing path over an admin toggle.
- **Deferred (follow-ups):** ConsequencePool side-effects on the presentation check;
  masquerade-aware prestige attribution (currently the primary persona); IC
  broadcast of the crowning.

## Visible Worn Equipment (DONE)

**Branch:** `visible-worn-equipment`

Looking at a character now shows their visible worn equipment — names only,
with deeper layers concealed by covering items. From there, drilling into a
specific piece reveals its full description. Same data on every transport:
telnet `look <person>'s <item>` (or `look <item> on <person>` / `look <item>
in <container>`), and a focus-stack side panel in the React frontend.

What landed:

- **Visibility computation service** in `world.items.services.appearance`:
  `visible_worn_items_for(character, observer=None)` walks `EquippedItem`
  rows and applies per-(body_region, equipment_layer) hiding via
  `TemplateSlot.covers_lower_layers`. Self-look (`observer is character`)
  and staff observers bypass the hiding pass — staff routinely need to
  investigate gear in-game without dropping into Django admin.
- **`CharacterState` appearance extension**: `get_display_worn(looker)` and
  `get_display_status(looker)` (placeholder for the combat-roadmap
  follow-up). `return_appearance` adds a "Wearing: ..." line under the
  description when items are visible; the section is omitted entirely when
  nothing is visible.
- **Telnet `CmdLook` parser** handles three new forms — possessive
  (`look bob's hat`), `on` (`look hat on bob`), `in` (`look coin in pouch`).
  Plain `look <name>` falls through to the existing `LookAction`.
- **`LookAtItemAction`** (registered): visibility gate (concealed items
  rejected unless self/staff), container open/close check, case-insensitive
  name match with substring fallback.
- **REST endpoints** at `/api/items/`:
  - `GET visible-worn/?character=N` — slim list of items visible on the
    character to the requester. Scoped to same-room observers, plus
    self-look and staff bypass.
  - `GET visible-item-detail/<id>/` — full item detail. Concealed items
    return 404 to avoid leaking existence.
- **Frontend focus stack** in the right sidebar:
  - `useFocusStack` hook in `inventory/hooks` manages the entry stack
    (room → character → item) with `push`, `pop`, `reset`.
  - `FocusPanel` orchestrates which view renders based on `current.kind`,
    using the existing `RoomPanel` for the room view and new
    `CharacterFocusView` / `ItemFocusView` for the drilled views.
  - Back button shows at depth > 1 and pops the stack.
  - **Dynamic tab label** — the right-sidebar Room tab's text follows the
    focus: room name → character name → item name (truncated to 8rem with
    full-name title tooltip on hover).
  - Stack resets to the room when the player switches character or moves.
- **Cross-cutting infrastructure** (lands here because the visibility
  service is the first natural use):
  - `core_management.permissions.is_staff_observer(observer)` — yes/no
    helper accepting ObjectDB / AccountDB / User-like, walks
    `character.account.is_staff` for ObjectDB. Policy-free; callers decide
    what to do with the answer.
  - `core_management.permissions.PlayerOnlyPermission` — base class for
    sensitive resources; staff get NO bypass. Use for very-private scenes,
    sealed journals, etc.
  - `core_management.permissions.PlayerOrStaffPermission` — base class for
    the common case; staff bypass everything. Subclasses override
    `has_permission_for_player` and `has_object_permission_for_player`.
  - The principle: staff bypass is explicitly opt-in per resource, never
    automatic. Picking the base class IS the per-resource opt-in.
  - Refactored `ItemFacetWritePermission`, `OutfitWritePermission`,
    `OutfitSlotWritePermission` to inherit `PlayerOrStaffPermission` and
    drop their inline `is_staff` short-circuits. Behavior preserved.
  - **`world.scenes.interaction_permissions.CanViewInteraction` flagged
    during the audit** — has a non-uniform staff bypass policy (excludes
    staff from very_private interactions). Worth a separate review before
    refactoring; left untouched in this PR.

Explicitly NOT in this slice (parked):

- **Narrative status display** — the appearance template's `{status}`
  slot is wired but renders empty until vitals/fatigue/conditions
  integration lands. Tracked in
  [`docs/roadmap/combat.md`](combat.md) under "Narrative Status in
  Character Descriptions."
- **Examining items in containers belonging to others** — only the
  requester's own / same-room containers work today.
- **Right-click context menu on worn items** ("compliment outfit", etc.).
- **`CanViewInteraction` permission refactor** — flagged for separate
  review as noted above.

## What's Needed for MVP
- ~~Equipment slot / body part model~~ — **done** (TemplateSlot with BodyRegion + EquipmentLayer)
- ~~Worn items tracking~~ — **done** (EquippedItem model + equip/unequip services)
- ~~Item type system~~ — **done** (ItemTemplate with container/stacking/consumable flags plus weapon/armor combat stat blocks gated by `gear_archetype` — #508)
- ~~Item quality~~ — **done** (QualityTier lookup table with stat multipliers)
- ~~Item facet system~~ — **done** (ItemFacet through-model, attach/remove services, modifier integration — Spec D PR1)
- ~~Inventory service functions~~ — **done** (pick_up, drop, give, equip, unequip, put_in, take_out — backing 7 Action classes; telnet commands and existing web action dispatcher both supported)
- ~~Saved outfits (Phase A)~~ — **done** (Outfit / OutfitSlot models, apply_outfit / undress / save_outfit / delete_outfit / add_outfit_slot / remove_outfit_slot services, ApplyOutfit/Undress actions, `wear outfit <name>` + `undress` telnet commands, REST CRUD, wardrobe page)
- ~~Item stats model~~ — **done** (#508: `ItemTemplate` base combat stats — `weapon_damage_type`, `base_weapon_damage`, `base_armor_soak`, `max_durability`, gated by `gear_archetype`; `ItemInstance` derives `effective_weapon_damage` / `effective_armor_soak` / `is_broken` from quality tier and `durability`; `decrement_item_durability` service; combat wiring — armor soak in `apply_damage_to_participant`, equipped-weapon damage via `TechniqueDamageProfile.uses_equipped_weapon`, durability decremented on landed/soaked hits)
- Visible equipment display — what others see when looking at a character; perception-layer integration into `look` output (not started)
- Item interaction service functions — using items, consuming charges (DONE, #509)
- Crafting integration — `OwnershipEvent.CREATED` rows written when crafted items are produced (not started; tracked under crafting roadmap)
- ~~Outfits Phase B (Fashion)~~ — **done** (`FashionStyle` + `FashionStyleBonus` models, `Society.current_fashion_style` FK, `fashion_outfit_bonus` service, wired into `get_modifier_total` via `perceiving_society`; scene-derived society + combat surfacing delivered in Spec D PR4 / #512 via `societies_for_scene` + `collect_check_modifiers`)
- ~~Outfits Phase C (Modeling)~~ — **done** (#514: `FashionPresentation` + peer `PresentationEndorsement`, `Event.host_society`, `prestige_from_fashion` axis, `FacetVogueMomentum` + seasonal trendsetter ceremony rewriting `Society.current_fashion_style`, `RankingType.FASHION` leaderboard reusing #676, present/judge API + event-detail UI)
- ~~Mantle attunement layer~~ — **done** (Spec D PR4 / #512: `Mantle` artifacts, Codex-gated
  per-character `MANTLE`-thread attunement, mantle combat bonuses; see the PR4 section above)
- Outfits Phase D (Legendary) — outfit legend accrual and famous outfits as referenceable
  artifacts in the magic / story layer (not started; mantle *attunement* shipped in PR4,
  but outfit-*bound* legendary mantles remain)
- Servant retrieval — fetching items from off-character storage; parked in `docs/roadmap/rooms-and-estates.md` (not started)

## Magic Integration (Spec A)
- **Items as thread anchors** — The new `Thread` model supports an `ITEM` anchor kind
  (`thread.item` FK to `ItemInstance`). Heirloom weapons, legendary relics, and other
  thread-capable items can accrue resonance and level as persistent threads
- **Ritual components** — `RitualComponentRequirement` FKs to `ItemTemplate` (with an
  optional `QualityTier`) to declare what items a ritual consumes when cast
- Cross-reference: `docs/systems/magic.md` for the full model lineup

## Notes
