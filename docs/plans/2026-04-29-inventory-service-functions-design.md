# Inventory Service Functions — Design

**Date:** 2026-04-29
**Status:** Design accepted, implementation not started
**Roadmap link:** [Items & Equipment](../roadmap/items-equipment.md) — "Inventory service functions" MVP item

## Goal

Provide a single backend layer that both the React frontend and telnet commands call into for picking up, dropping, giving, equipping, unequipping, and moving items in and out of containers. The frontend's right-click menus, drag-to-equip gestures, and telnet commands all flow through identical service functions, so validation, ownership ledger writes, and side effects stay in one place.

## Scope

**In scope:**
- Service functions for: `pick_up`, `drop`, `give`, `equip`, `unequip`, `put_in`, `take_out`
- A new `ItemState` for permission gating, parallel to `CharacterState` / `RoomState` / `ExitState`
- Telnet command parsing for the standard verbs
- WebSocket action shape for the frontend
- Tests for service functions, permission methods, and telnet parsing

**Out of scope (deliberately):**
- Visible-equipment display in `look` output — lives in perception, separate slice
- Combat stat application from worn weapons/armor — waits for the item stats model
- Frontend UI components (inventory panel, body silhouette, drag-drop) — the slice ends at the WebSocket handler
- Crafting integration — crafting will write its own `OwnershipEvent(CREATION)` when it lands

## Architecture

### Service surface

Location: `src/flows/service_functions/inventory.py`

| Function | Effect |
|----------|--------|
| `pick_up(character, item)` | Move item from room (or open container) into character's possession |
| `drop(character, item)` | Move item from possession into character's current room; auto-unequip first if equipped |
| `give(giver, recipient, item)` | Transfer item from giver to recipient; write `OwnershipEvent(GIFT)` |
| `equip(character, item, slot=None)` | Create `EquippedItem` row(s) for the template's declared slots |
| `unequip(character, item)` | Remove `EquippedItem` row(s); item stays in inventory |
| `put_in(character, item, container)` | Move item into a container item (sets `contained_in`) |
| `take_out(character, item)` | Move item out of its container into character's possession |

All functions take `BaseState` wrappers (consistent with `flows/service_functions/movement.py`), not raw `ObjectDB`. All multi-row mutations run inside `transaction.atomic`.

### Permission gating

A new `ItemState` (in `src/flows/object_states/item_state.py`) wraps `ItemInstance` and exposes:

- `can_take(taker)` — item must be in the taker's room (or in an open, reachable container), not bound to another character, not staff-locked
- `can_drop(dropper)` — item must be in dropper's possession (held or equipped), not soulbound
- `can_give(giver, recipient)` — recipient in same room, item in giver's possession, recipient not at carry-cap
- `can_equip(wearer)` — item in wearer's possession, template has slots, item not broken (durability lands later)

These methods exist as the hook point for flows and triggers. A cursed item that screams when picked up plugs into `can_take` via the reactive layer without changing the service surface.

### Equip slot-conflict policy

When equipping a new item, for each slot the template declares (`body_region`, `equipment_layer`):

1. **Same body region + same layer occupied** → unequip the existing item, equip the new one. One message: *"You swap your jacket for a leather coat."*
2. **Same body region, different layer** → just add the row. No shuffling, no message about other layers. Layered clothing stacks freely; we don't simulate the realism of taking off a cloak to swap an undershirt.
3. **Lower layers occupied** when equipping a higher layer → trivially fine; just add the row.
4. **Multi-region items** (full plate occupies torso + both arms) → apply rules 1–3 to *each* region, all in one atomic transaction.

### Telnet commands

Each command parses input and delegates to the service function:

| Command | Service call |
|---------|-------------|
| `get <item>` | `pick_up` |
| `get <item> from <container>` | `take_out` |
| `drop <item>` | `drop` (auto-unequips first if needed) |
| `give <item> to <person>` | `give` |
| `wear <item>` | `equip` (auto-pick when unambiguous) |
| `wear <item> on <region>` | `equip` (region-disambiguated) |
| `wear <item> under <other>` / `wear <item> over <other>` | `equip` (layer relative to another worn item) |
| `remove <item>` | `unequip` |
| `put <item> in <container>` | `put_in` |

The `under` / `over` modifiers are parser conveniences. They resolve to a concrete `(region, layer)` tuple before calling `equip`; the service function only ever sees explicit slots or auto-pick.

### Frontend surface

A unified WebSocket action:

```
{
  type: "INVENTORY_ACTION",
  action: "equip" | "unequip" | "pick_up" | "drop" | "give" | "put_in" | "take_out",
  item_id: number,
  // action-specific:
  recipient_id?: number,    // give
  container_id?: number,    // put_in
  region?: BodyRegion,      // equip
  layer?: EquipmentLayer,   // equip
}
```

The right-click context menu on item links shows actions valid for the item's current location and the viewer's relationship to it — using the same `can_*` checks the service uses, so the menu and the action stay in sync. Drag-from-inventory-onto-body-silhouette dispatches `equip`. Drag-out-of-slot dispatches `unequip`.

### Errors

A typed `InventoryError` subclass per the project's CodeQL pattern (see `EventError`, `JournalError`):

```python
class InventoryError(Exception):
    user_message: str  # safe to surface to the client
```

Subclasses for `SlotOccupied`, `NotInPossession`, `ContainerFull`, `RecipientNotAdjacent`, `Soulbound`, etc. The view layer reads `exc.user_message`; never `str(exc)`.

### Ownership events

- **Creation events** (`OwnershipEvent.event_type=CREATION`) are written by whatever system creates the item — crafting (when built) writes one with `to_account=crafter`, GM spawn tools write one with `to_account=None` (unowned), world seed writes none. The inventory service does not write CREATION events.
- **`pick_up`** writes `OwnershipEvent(PICKUP, to_account=picker_account)` only when the item has no current `owner` AND no prior ownership events — i.e., a genuinely unowned item entering possession for the first time. A crafted item with an existing CREATION event is already attributed; picking it up later is a location move only.
- **`give`** always writes `OwnershipEvent(GIFT, from_account, to_account)` — always a real ownership transition.
- `drop`, `equip`, `unequip`, `put_in`, `take_out` never write ownership events. These are spatial moves, not custody changes.

## Testing approach

- `src/world/items/tests/test_inventory_services.py` — one test class per service function:
  - happy path
  - permission denial via `can_*` returning `False`
  - slot conflicts (equip)
  - container constraints (put_in)
  - ownership ledger writes (give, first-pickup)
  - atomicity: simulate a partial failure mid-transaction, assert no rows changed
- `src/world/items/tests/test_item_state.py` — focused tests for each `can_*` permission method, including the cursed/soulbound paths once those exist
- One telnet integration test for `wear <item> on <region>` and one for `give <item> to <name>` to lock in the parsing

## Migration plan

No new models. No migrations needed. The work is service-layer-only on top of the existing items models.

## Risks and mitigations

- **Telnet parsing ambiguity** when multiple items match a name — handled by the existing object search infrastructure (same as `get`/`drop` in any MUD); `wear under <other>` and `wear over <other>` give players a deterministic disambiguator.
- **Slot conflict UX** — auto-swapping at the same layer may surprise telnet players who expect explicit `remove` first. Single confirmation message ("You swap your jacket for a leather coat") gives them the audit trail without forcing the extra step.
- **Identity-map staleness after equip/unequip** — `EquippedItem.objects.create(...)` doesn't auto-update any cached `equipped_items` collection on the character. Tests should assert that whatever `look`/inventory rendering reads from is consistent post-mutation; if there's a `cached_property` on the character that holds equipped items, update it in place after the mutation per the SharedMemoryModel guidance.

## Out-of-scope follow-ups

These naturally come after this slice and have clear handoffs:

1. **Visible equipment in `look`** — perception service reads `EquippedItem` rows for the looked-at character and renders them with layer hiding (`covers_lower_layers`).
2. **Item stats model** — weapons and armor get stat blocks; combat reads them from equipped items.
3. **Frontend inventory panel** — React components consuming the WebSocket actions defined here.
4. **Crafting integration** — when crafting lands, it writes the `OwnershipEvent(CREATION)` and sets `owner=crafter` directly; no inventory-service change needed.
