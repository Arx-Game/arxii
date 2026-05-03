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

**Spec:** `docs/superpowers/specs/2026-04-26-items-fashion-mantles-spec-d-design.md`
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
- ~~Item type system~~ — **partially done** (ItemTemplate with container/stacking/consumable flags; no weapon/armor stat blocks yet)
- ~~Item quality~~ — **done** (QualityTier lookup table with stat multipliers)
- ~~Item facet system~~ — **done** (ItemFacet through-model, attach/remove services, modifier integration — Spec D PR1)
- ~~Inventory service functions~~ — **done** (pick_up, drop, give, equip, unequip, put_in, take_out — backing 7 Action classes; telnet commands and existing web action dispatcher both supported)
- ~~Saved outfits (Phase A)~~ — **done** (Outfit / OutfitSlot models, apply_outfit / undress / save_outfit / delete_outfit / add_outfit_slot / remove_outfit_slot services, ApplyOutfit/Undress actions, `wear outfit <name>` + `undress` telnet commands, REST CRUD, wardrobe page)
- Item stats model — combat properties, condition/durability (not started)
- Visible equipment display — what others see when looking at a character; perception-layer integration into `look` output (not started)
- Item interaction service functions — using items, consuming charges (not started)
- Crafting integration — `OwnershipEvent.CREATED` rows written when crafted items are produced (not started; tracked under crafting roadmap)
- Outfits Phase B (Fashion) — `FashionStyle` model, item-fashion compatibility rules, current-fashion rotation, aggregate per-outfit fashion bonuses (not started)
- Outfits Phase C (Modeling) — present an outfit at events, peer judging, leaderboards (not started)
- Outfits Phase D (Legendary + Mantle) — outfit legend accrual, outfit-bound mantles, famous outfits as referenceable artifacts in the magic / story layer (not started)
- Servant retrieval — fetching items from off-character storage; parked in `docs/roadmap/rooms-and-estates.md` (not started)

## Magic Integration (Spec A)
- **Items as thread anchors** — The new `Thread` model supports an `ITEM` anchor kind
  (`thread.item` FK to `ItemInstance`). Heirloom weapons, legendary relics, and other
  thread-capable items can accrue resonance and level as persistent threads
- **Ritual components** — `RitualComponentRequirement` FKs to `ItemTemplate` (with an
  optional `QualityTier`) to declare what items a ritual consumes when cast
- Cross-reference: `docs/systems/magic.md` for the full model lineup

## Notes
