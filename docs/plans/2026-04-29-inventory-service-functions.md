# Inventory Service Functions Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the backend service-function layer for picking up, dropping, giving, equipping, unequipping, and moving items into and out of containers — used identically by telnet commands and the React frontend's WebSocket actions.

**Architecture:** Pure service-layer work on top of the existing `world.items` models (no new models, no migrations). Service functions live in `src/flows/service_functions/inventory.py`, take `BaseState` wrappers for permission gating via a new `ItemState`, and run multi-row mutations inside `transaction.atomic`. Telnet commands and a WebSocket `inventory_action` inputfunc both dispatch into the same service functions.

**Tech Stack:** Django 5.x, Evennia, FactoryBoy, Django REST Framework (existing patterns reused).

**Design source:** `docs/plans/2026-04-29-inventory-service-functions-design.md`

**Adjustments from design doc:**
- `OwnershipEventType` enum has values `CREATED`, `GIVEN`, `STOLEN`, `TRANSFERRED`. There is no `PICKUP` value. We will use `GIVEN` for `give`, and `pick_up` will not write an ownership event at all — it just sets `owner` if the item was unowned. This is simpler than adding a new enum value and matches the design's intent: picking unowned junk off the floor is not a real custody transition.

---

## Pre-flight

Before starting, verify the working tree is clean and on the right branch:

```bash
git -C /c/Users/apost/PycharmProjects/arxii status
git -C /c/Users/apost/PycharmProjects/arxii branch --show-current
```

Expected: `inventory-service-functions-design` branch, clean tree (only the design + plan docs exist beyond main).

Each task ends with a commit. Use TDD: failing test → run → minimal code → run → commit.

To run tests: `echo "yes" | uv run arx test world.items` (the `echo "yes"` answers Evennia's DB-prompt).

To run a specific test: `echo "yes" | uv run arx test world.items.tests.test_inventory_services.PickUpTests.test_basic_pickup`

---

## Task 1: InventoryError typed exceptions

**Files:**
- Create: `src/world/items/exceptions.py`
- Test: `src/world/items/tests/test_exceptions.py`

**Step 1: Write the failing test**

```python
# src/world/items/tests/test_exceptions.py
"""Tests for inventory exception types."""

from django.test import SimpleTestCase

from world.items.exceptions import (
    ContainerClosed,
    ContainerFull,
    InventoryError,
    ItemTooLarge,
    NotEquipped,
    NotInPossession,
    PermissionDenied,
    RecipientNotAdjacent,
    SlotOccupied,
)


class InventoryExceptionTests(SimpleTestCase):
    """Each inventory exception exposes a safe ``user_message``."""

    def test_inventory_error_is_base_class(self) -> None:
        """All inventory errors inherit from InventoryError."""
        for cls in (
            SlotOccupied,
            NotInPossession,
            NotEquipped,
            ContainerFull,
            ContainerClosed,
            ItemTooLarge,
            RecipientNotAdjacent,
            PermissionDenied,
        ):
            self.assertTrue(issubclass(cls, InventoryError))

    def test_each_subclass_has_user_message(self) -> None:
        """Every subclass exposes a non-empty user_message classvar."""
        for cls in (
            SlotOccupied,
            NotInPossession,
            NotEquipped,
            ContainerFull,
            ContainerClosed,
            ItemTooLarge,
            RecipientNotAdjacent,
            PermissionDenied,
        ):
            self.assertTrue(cls.user_message)
            self.assertIsInstance(cls.user_message, str)
```

**Step 2: Run test to verify it fails**

```bash
echo "yes" | uv run arx test world.items.tests.test_exceptions -v
```

Expected: ImportError — `world.items.exceptions` does not exist.

**Step 3: Implement `src/world/items/exceptions.py`**

```python
"""Typed exceptions for inventory operations.

Each subclass carries a ``user_message`` safe to surface to clients,
following the project's CodeQL-safe pattern. View/inputfunc layers
read ``exc.user_message`` — never ``str(exc)``.
"""

from __future__ import annotations


class InventoryError(Exception):
    """Base class for inventory-operation failures."""

    user_message: str = "That action could not be completed."


class PermissionDenied(InventoryError):
    user_message = "You cannot do that with that item."


class NotInPossession(InventoryError):
    user_message = "You are not carrying that."


class NotEquipped(InventoryError):
    user_message = "You are not wearing that."


class SlotOccupied(InventoryError):
    user_message = "Something is already in that slot."


class ContainerFull(InventoryError):
    user_message = "That container is already full."


class ContainerClosed(InventoryError):
    user_message = "That container is closed."


class ItemTooLarge(InventoryError):
    user_message = "That item is too large to fit in there."


class RecipientNotAdjacent(InventoryError):
    user_message = "They are not here to receive it."
```

**Step 4: Run test to verify it passes**

```bash
echo "yes" | uv run arx test world.items.tests.test_exceptions -v
```

Expected: PASS.

**Step 5: Commit**

```bash
git add src/world/items/exceptions.py src/world/items/tests/test_exceptions.py
git commit -m "feat(items): InventoryError typed exception hierarchy"
```

---

## Task 2: ItemState with default-allow permissions

**Files:**
- Create: `src/flows/object_states/item_state.py`
- Modify: `src/flows/object_states/__init__.py` (export `ItemState`)
- Test: `src/world/items/tests/test_item_state.py`

**Step 1: Write the failing test**

```python
# src/world/items/tests/test_item_state.py
"""Tests for ItemState permission methods."""

from unittest.mock import MagicMock

from django.test import TestCase

from flows.object_states.item_state import ItemState
from world.items.factories import ItemInstanceFactory


class ItemStateDefaultsTests(TestCase):
    """ItemState exposes can_* methods that default to True."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.item = ItemInstanceFactory()

    def setUp(self) -> None:
        # SceneDataManager is normally injected; for can_* defaults a
        # bare MagicMock context is fine since the methods do not touch it.
        self.state = ItemState(self.item, context=MagicMock())

    def test_can_take_default_true(self) -> None:
        self.assertTrue(self.state.can_take(taker=MagicMock()))

    def test_can_drop_default_true(self) -> None:
        self.assertTrue(self.state.can_drop(dropper=MagicMock()))

    def test_can_give_default_true(self) -> None:
        self.assertTrue(
            self.state.can_give(giver=MagicMock(), recipient=MagicMock())
        )

    def test_can_equip_default_true(self) -> None:
        self.assertTrue(self.state.can_equip(wearer=MagicMock()))
```

**Step 2: Run to verify it fails**

```bash
echo "yes" | uv run arx test world.items.tests.test_item_state -v
```

Expected: ImportError — `flows.object_states.item_state` does not exist.

**Step 3: Implement `src/flows/object_states/item_state.py`**

```python
"""Object state wrapper for item instances."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flows.object_states.base_state import BaseState

if TYPE_CHECKING:
    from flows.object_states.character_state import CharacterState


class ItemState(BaseState):
    """Mutable wrapper for an item during a flow run.

    Permission methods default to True. Triggers and behaviors plug in
    via the reactive layer to deny actions for cursed, soulbound, or
    locked items without changing the service surface.
    """

    def can_take(self, taker: "CharacterState") -> bool:
        """Whether ``taker`` may pick up this item."""
        return True

    def can_drop(self, dropper: "CharacterState") -> bool:
        """Whether ``dropper`` may drop this item."""
        return True

    def can_give(
        self,
        giver: "CharacterState",
        recipient: "CharacterState",
    ) -> bool:
        """Whether ``giver`` may give this item to ``recipient``."""
        return True

    def can_equip(self, wearer: "CharacterState") -> bool:
        """Whether ``wearer`` may equip this item."""
        return True
```

Update `src/flows/object_states/__init__.py` to export `ItemState` if that file currently exports the others. (Check first — if it's empty, leave it alone.)

**Step 4: Run to verify it passes**

```bash
echo "yes" | uv run arx test world.items.tests.test_item_state -v
```

Expected: PASS.

**Step 5: Commit**

```bash
git add src/flows/object_states/item_state.py src/world/items/tests/test_item_state.py src/flows/object_states/__init__.py
git commit -m "feat(flows): ItemState with default-allow permission methods"
```

---

## Task 3: pick_up service function

**Files:**
- Create: `src/flows/service_functions/inventory.py`
- Test: `src/world/items/tests/test_inventory_services.py`

**Use existing factories:**
- `ItemInstanceFactory` (in `src/world/items/factories.py`)
- For characters/rooms/accounts use the standard evennia_extensions test factories — check `src/evennia_extensions/factories.py` first for a `CharacterFactory`/`AccountFactory`/`RoomFactory`. Memory note: never use `create_object()` directly; always go through these factories.

**Step 1: Write failing test**

```python
# src/world/items/tests/test_inventory_services.py
"""Tests for inventory service functions."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from flows.object_states.character_state import CharacterState
from flows.object_states.item_state import ItemState
from flows.service_functions.inventory import pick_up
from world.items.exceptions import PermissionDenied
from world.items.factories import ItemInstanceFactory
# Adjust these imports to whatever the project's character/room factories are.
from evennia_extensions.factories import AccountFactory, CharacterFactory, RoomFactory


class PickUpTests(TestCase):
    """`pick_up` moves an item from a room into a character's inventory."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        cls.room = RoomFactory()
        cls.character = CharacterFactory(account=cls.account, location=cls.room)

    def setUp(self) -> None:
        self.item = ItemInstanceFactory()
        # Place the item's underlying ObjectDB in the room.
        self.item.game_object.location = self.room
        self.item.game_object.save()

        ctx = MagicMock()
        self.character_state = CharacterState(self.character, context=ctx)
        self.item_state = ItemState(self.item, context=ctx)

    def test_basic_pickup_moves_object_into_character(self) -> None:
        pick_up(self.character_state, self.item_state)
        self.item.game_object.refresh_from_db()
        self.assertEqual(self.item.game_object.location, self.character)

    def test_pickup_sets_owner_when_unowned(self) -> None:
        self.item.owner = None
        self.item.save()
        pick_up(self.character_state, self.item_state)
        self.item.refresh_from_db()
        self.assertEqual(self.item.owner, self.account)

    def test_pickup_does_not_overwrite_existing_owner(self) -> None:
        other_account = AccountFactory()
        self.item.owner = other_account
        self.item.save()
        pick_up(self.character_state, self.item_state)
        self.item.refresh_from_db()
        self.assertEqual(self.item.owner, other_account)

    def test_pickup_denied_by_can_take_raises(self) -> None:
        with patch.object(ItemState, "can_take", return_value=False):
            with self.assertRaises(PermissionDenied):
                pick_up(self.character_state, self.item_state)
```

**Step 2: Run to verify it fails**

```bash
echo "yes" | uv run arx test world.items.tests.test_inventory_services.PickUpTests -v
```

Expected: ImportError on `flows.service_functions.inventory`.

**Step 3: Implement `src/flows/service_functions/inventory.py`**

```python
"""Inventory mutation service functions.

Used by both telnet commands and the WebSocket ``inventory_action``
inputfunc. All mutations run inside ``transaction.atomic`` so partial
failures roll back fully.
"""

from __future__ import annotations

from django.db import transaction

from flows.object_states.character_state import CharacterState
from flows.object_states.item_state import ItemState
from world.items.exceptions import PermissionDenied


@transaction.atomic
def pick_up(character: CharacterState, item: ItemState) -> None:
    """Move ``item`` from its current location into ``character``'s possession.

    If the item is currently unowned (``owner`` is null), ``character``'s
    account becomes the owner. Pre-existing ownership is preserved.
    """
    if not item.can_take(taker=character):
        raise PermissionDenied
    item.obj.game_object.location = character.obj
    item.obj.game_object.save()
    if item.obj.owner is None:
        item.obj.owner = character.obj.account
        item.obj.save(update_fields=["owner"])
```

**Step 4: Run to verify it passes**

```bash
echo "yes" | uv run arx test world.items.tests.test_inventory_services.PickUpTests -v
```

Expected: PASS (all 4 tests).

**If a test references a factory that doesn't exist** (e.g., `RoomFactory`), check the actual location with `Grep` for `class.*Factory` in `src/evennia_extensions/` and `src/typeclasses/` and adjust. The memory note "Use evennia_extensions factories in tests" should pin this.

**Step 5: Commit**

```bash
git add src/flows/service_functions/inventory.py src/world/items/tests/test_inventory_services.py
git commit -m "feat(flows): pick_up service function"
```

---

## Task 4: drop service function (with auto-unequip)

**Files:**
- Modify: `src/flows/service_functions/inventory.py`
- Modify: `src/world/items/tests/test_inventory_services.py`

**Step 1: Write failing tests**

Append to `test_inventory_services.py`:

```python
class DropTests(TestCase):
    """`drop` moves an item from a character's possession into their room."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        cls.room = RoomFactory()
        cls.character = CharacterFactory(account=cls.account, location=cls.room)

    def setUp(self) -> None:
        self.item = ItemInstanceFactory()
        self.item.game_object.location = self.character
        self.item.game_object.save()
        ctx = MagicMock()
        self.character_state = CharacterState(self.character, context=ctx)
        self.item_state = ItemState(self.item, context=ctx)

    def test_drop_moves_item_to_character_location(self) -> None:
        drop(self.character_state, self.item_state)
        self.item.game_object.refresh_from_db()
        self.assertEqual(self.item.game_object.location, self.room)

    def test_drop_auto_unequips_first(self) -> None:
        from world.items.constants import BodyRegion, EquipmentLayer
        from world.items.models import EquippedItem

        EquippedItem.objects.create(
            character=self.character,
            item_instance=self.item,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        drop(self.character_state, self.item_state)
        self.assertFalse(
            EquippedItem.objects.filter(item_instance=self.item).exists()
        )
        self.item.game_object.refresh_from_db()
        self.assertEqual(self.item.game_object.location, self.room)

    def test_drop_denied_raises(self) -> None:
        with patch.object(ItemState, "can_drop", return_value=False):
            with self.assertRaises(PermissionDenied):
                drop(self.character_state, self.item_state)
```

Add `drop` to the imports at the top.

**Step 2: Run to verify it fails**

```bash
echo "yes" | uv run arx test world.items.tests.test_inventory_services.DropTests -v
```

Expected: ImportError on `drop`.

**Step 3: Implement `drop` in `inventory.py`**

```python
@transaction.atomic
def drop(character: CharacterState, item: ItemState) -> None:
    """Move ``item`` from ``character``'s possession into their current room.

    If the item is currently equipped, all ``EquippedItem`` rows are
    removed first (single confirmation in the message layer).
    """
    if not item.can_drop(dropper=character):
        raise PermissionDenied
    item.obj.equipped_slots.all().delete()
    item.obj.game_object.location = character.obj.location
    item.obj.game_object.save()
```

**Step 4: Run to verify**

```bash
echo "yes" | uv run arx test world.items.tests.test_inventory_services.DropTests -v
```

Expected: PASS (3 tests).

**Step 5: Commit**

```bash
git add src/flows/service_functions/inventory.py src/world/items/tests/test_inventory_services.py
git commit -m "feat(flows): drop service function with auto-unequip"
```

---

## Task 5: give service function (with OwnershipEvent)

**Files:**
- Modify: `src/flows/service_functions/inventory.py`
- Modify: `src/world/items/tests/test_inventory_services.py`

**Step 1: Write failing tests**

```python
class GiveTests(TestCase):
    """`give` transfers an item between two characters and writes a ledger event."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.giver_account = AccountFactory()
        cls.recipient_account = AccountFactory()
        cls.room = RoomFactory()
        cls.giver = CharacterFactory(account=cls.giver_account, location=cls.room)
        cls.recipient = CharacterFactory(
            account=cls.recipient_account, location=cls.room
        )

    def setUp(self) -> None:
        self.item = ItemInstanceFactory(owner=self.giver_account)
        self.item.game_object.location = self.giver
        self.item.game_object.save()
        ctx = MagicMock()
        self.giver_state = CharacterState(self.giver, context=ctx)
        self.recipient_state = CharacterState(self.recipient, context=ctx)
        self.item_state = ItemState(self.item, context=ctx)

    def test_give_transfers_location_and_owner(self) -> None:
        give(self.giver_state, self.recipient_state, self.item_state)
        self.item.refresh_from_db()
        self.item.game_object.refresh_from_db()
        self.assertEqual(self.item.game_object.location, self.recipient)
        self.assertEqual(self.item.owner, self.recipient_account)

    def test_give_writes_ownership_event(self) -> None:
        from world.items.constants import OwnershipEventType
        from world.items.models import OwnershipEvent

        give(self.giver_state, self.recipient_state, self.item_state)
        event = OwnershipEvent.objects.get(item_instance=self.item)
        self.assertEqual(event.event_type, OwnershipEventType.GIVEN)
        self.assertEqual(event.from_account, self.giver_account)
        self.assertEqual(event.to_account, self.recipient_account)

    def test_give_denied_raises(self) -> None:
        with patch.object(ItemState, "can_give", return_value=False):
            with self.assertRaises(PermissionDenied):
                give(self.giver_state, self.recipient_state, self.item_state)
```

Add `give` to imports.

**Step 2: Run to verify failure**

```bash
echo "yes" | uv run arx test world.items.tests.test_inventory_services.GiveTests -v
```

Expected: ImportError on `give`.

**Step 3: Implement `give`**

```python
@transaction.atomic
def give(
    giver: CharacterState,
    recipient: CharacterState,
    item: ItemState,
) -> None:
    """Transfer ``item`` from ``giver`` to ``recipient``.

    Writes an ``OwnershipEvent(GIVEN)`` row, transfers ``owner``, and
    moves the underlying ``ObjectDB`` to the recipient.
    """
    from world.items.constants import OwnershipEventType
    from world.items.models import OwnershipEvent

    if not item.can_give(giver=giver, recipient=recipient):
        raise PermissionDenied

    previous_owner = item.obj.owner
    item.obj.equipped_slots.all().delete()
    item.obj.game_object.location = recipient.obj
    item.obj.game_object.save()
    item.obj.owner = recipient.obj.account
    item.obj.save(update_fields=["owner"])
    OwnershipEvent.objects.create(
        item_instance=item.obj,
        event_type=OwnershipEventType.GIVEN,
        from_account=previous_owner,
        to_account=recipient.obj.account,
    )
```

**Step 4: Verify pass**

```bash
echo "yes" | uv run arx test world.items.tests.test_inventory_services.GiveTests -v
```

Expected: PASS (3 tests).

**Step 5: Commit**

```bash
git add src/flows/service_functions/inventory.py src/world/items/tests/test_inventory_services.py
git commit -m "feat(flows): give service function with OwnershipEvent ledger write"
```

---

## Task 6: equip service function with slot-conflict policy

This is the largest task. Read the design doc's "Equip slot-conflict policy" before implementing.

**Files:**
- Modify: `src/flows/service_functions/inventory.py`
- Modify: `src/world/items/tests/test_inventory_services.py`

**Step 1: Write failing tests**

```python
class EquipTests(TestCase):
    """`equip` creates EquippedItem rows; same-layer occupied slots auto-swap."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        cls.room = RoomFactory()
        cls.character = CharacterFactory(account=cls.account, location=cls.room)

    def setUp(self) -> None:
        from world.items.constants import BodyRegion, EquipmentLayer
        from world.items.factories import ItemTemplateFactory
        from world.items.models import TemplateSlot

        self.template = ItemTemplateFactory()
        TemplateSlot.objects.create(
            template=self.template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        self.item = ItemInstanceFactory(template=self.template)
        self.item.game_object.location = self.character
        self.item.game_object.save()

        ctx = MagicMock()
        self.character_state = CharacterState(self.character, context=ctx)
        self.item_state = ItemState(self.item, context=ctx)

    def test_equip_into_empty_slot_creates_row(self) -> None:
        from world.items.models import EquippedItem
        equip(self.character_state, self.item_state)
        self.assertEqual(
            EquippedItem.objects.filter(
                character=self.character, item_instance=self.item
            ).count(),
            1,
        )

    def test_equip_same_layer_swaps_existing(self) -> None:
        from world.items.constants import BodyRegion, EquipmentLayer
        from world.items.models import EquippedItem

        existing = ItemInstanceFactory(template=self.template)
        existing.game_object.location = self.character
        existing.game_object.save()
        EquippedItem.objects.create(
            character=self.character,
            item_instance=existing,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )

        equip(self.character_state, self.item_state)

        equipped = EquippedItem.objects.filter(character=self.character)
        self.assertEqual(equipped.count(), 1)
        self.assertEqual(equipped.first().item_instance, self.item)

    def test_equip_different_layer_at_same_region_keeps_both(self) -> None:
        from world.items.constants import BodyRegion, EquipmentLayer
        from world.items.factories import ItemTemplateFactory
        from world.items.models import EquippedItem, TemplateSlot

        # Existing OUTER torso item; new item is BASE torso.
        outer_template = ItemTemplateFactory()
        TemplateSlot.objects.create(
            template=outer_template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.OUTER,
        )
        outer = ItemInstanceFactory(template=outer_template)
        outer.game_object.location = self.character
        outer.game_object.save()
        EquippedItem.objects.create(
            character=self.character,
            item_instance=outer,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.OUTER,
        )

        equip(self.character_state, self.item_state)

        self.assertEqual(
            EquippedItem.objects.filter(character=self.character).count(),
            2,
        )

    def test_equip_multi_region_creates_all_rows(self) -> None:
        from world.items.constants import BodyRegion, EquipmentLayer
        from world.items.factories import ItemTemplateFactory
        from world.items.models import EquippedItem, TemplateSlot

        plate_template = ItemTemplateFactory()
        for region in (BodyRegion.TORSO, BodyRegion.LEFT_ARM, BodyRegion.RIGHT_ARM):
            TemplateSlot.objects.create(
                template=plate_template,
                body_region=region,
                equipment_layer=EquipmentLayer.OUTER,
            )
        plate = ItemInstanceFactory(template=plate_template)
        plate.game_object.location = self.character
        plate.game_object.save()
        plate_state = ItemState(plate, context=MagicMock())

        equip(self.character_state, plate_state)

        self.assertEqual(
            EquippedItem.objects.filter(
                character=self.character, item_instance=plate
            ).count(),
            3,
        )

    def test_equip_denied_raises(self) -> None:
        with patch.object(ItemState, "can_equip", return_value=False):
            with self.assertRaises(PermissionDenied):
                equip(self.character_state, self.item_state)
```

Add `equip` to imports.

**Step 2: Run to verify failure**

```bash
echo "yes" | uv run arx test world.items.tests.test_inventory_services.EquipTests -v
```

Expected: ImportError on `equip`.

**Step 3: Implement `equip`**

```python
@transaction.atomic
def equip(character: CharacterState, item: ItemState) -> None:
    """Equip ``item`` on ``character`` in every slot its template declares.

    For each declared slot, if the same body region + same layer is
    already occupied by a different item, that item is unequipped first
    (single-message swap). Items at the same body region but a different
    layer are left alone.

    Multi-region items (full plate occupies torso + both arms) atomically
    create one EquippedItem row per region.
    """
    from world.items.models import EquippedItem

    if not item.can_equip(wearer=character):
        raise PermissionDenied

    for slot in item.obj.template.cached_slots:
        EquippedItem.objects.filter(
            character=character.obj,
            body_region=slot.body_region,
            equipment_layer=slot.equipment_layer,
        ).delete()
        EquippedItem.objects.create(
            character=character.obj,
            item_instance=item.obj,
            body_region=slot.body_region,
            equipment_layer=slot.equipment_layer,
        )
```

Note: `cached_slots` invalidation isn't a concern here since we're reading slots, not writing them. The character's equipped_items collection (if any) needs in-place update — see Task 11 if a stale-cache issue surfaces.

**Step 4: Verify pass**

```bash
echo "yes" | uv run arx test world.items.tests.test_inventory_services.EquipTests -v
```

Expected: PASS (5 tests).

**Step 5: Commit**

```bash
git add src/flows/service_functions/inventory.py src/world/items/tests/test_inventory_services.py
git commit -m "feat(flows): equip service function with slot-conflict policy"
```

---

## Task 7: unequip service function

**Files:**
- Modify: `src/flows/service_functions/inventory.py`
- Modify: `src/world/items/tests/test_inventory_services.py`

**Step 1: Write failing tests**

```python
class UnequipTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        cls.room = RoomFactory()
        cls.character = CharacterFactory(account=cls.account, location=cls.room)

    def setUp(self) -> None:
        from world.items.constants import BodyRegion, EquipmentLayer
        from world.items.factories import ItemTemplateFactory
        from world.items.models import EquippedItem, TemplateSlot

        template = ItemTemplateFactory()
        TemplateSlot.objects.create(
            template=template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        self.item = ItemInstanceFactory(template=template)
        self.item.game_object.location = self.character
        self.item.game_object.save()
        EquippedItem.objects.create(
            character=self.character,
            item_instance=self.item,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        ctx = MagicMock()
        self.character_state = CharacterState(self.character, context=ctx)
        self.item_state = ItemState(self.item, context=ctx)

    def test_unequip_removes_all_rows(self) -> None:
        from world.items.models import EquippedItem
        unequip(self.character_state, self.item_state)
        self.assertFalse(
            EquippedItem.objects.filter(item_instance=self.item).exists()
        )

    def test_unequip_not_equipped_raises(self) -> None:
        from world.items.models import EquippedItem
        EquippedItem.objects.filter(item_instance=self.item).delete()
        with self.assertRaises(NotEquipped):
            unequip(self.character_state, self.item_state)

    def test_unequip_leaves_item_in_inventory(self) -> None:
        unequip(self.character_state, self.item_state)
        self.item.game_object.refresh_from_db()
        self.assertEqual(self.item.game_object.location, self.character)
```

Add `unequip` and `NotEquipped` to imports.

**Step 2: Run to verify failure**

Expected: ImportError on `unequip`.

**Step 3: Implement `unequip`**

```python
@transaction.atomic
def unequip(character: CharacterState, item: ItemState) -> None:
    """Remove all ``EquippedItem`` rows for ``item`` on ``character``.

    The item stays in the character's inventory (its ``ObjectDB.location``
    is unchanged).
    """
    from world.items.exceptions import NotEquipped
    from world.items.models import EquippedItem

    rows = EquippedItem.objects.filter(
        character=character.obj, item_instance=item.obj
    )
    if not rows.exists():
        raise NotEquipped
    rows.delete()
```

**Step 4: Verify pass.**

**Step 5: Commit**

```bash
git commit -am "feat(flows): unequip service function"
```

---

## Task 8: put_in / take_out (container ops)

**Files:** same as above.

**Step 1: Write failing tests** for `put_in` and `take_out`. Cover:
- happy path (`put_in` sets `contained_in`; `take_out` clears it)
- `ContainerClosed` when container's `supports_open_close=True` and `is_open=False`
- `ContainerFull` when contents count >= `container_capacity`
- `ItemTooLarge` when item.template.size > container.template.container_max_item_size

Use `ItemTemplateFactory` with `is_container=True`, `container_capacity=N`, `container_max_item_size=N`, `supports_open_close=True`.

**Step 2-4: Iterate test → implement → verify.**

**Step 3 implementation:**

```python
@transaction.atomic
def put_in(
    character: CharacterState,
    item: ItemState,
    container: ItemState,
) -> None:
    """Move ``item`` into ``container`` (an item that is itself a container)."""
    from world.items.exceptions import (
        ContainerClosed,
        ContainerFull,
        ItemTooLarge,
        NotInPossession,
    )

    if not container.obj.template.is_container:
        raise ItemTooLarge  # Treat non-containers as "won't fit"
    if container.obj.template.supports_open_close and not container.obj.is_open:
        raise ContainerClosed
    if (
        container.obj.template.container_capacity
        and container.obj.contents.count() >= container.obj.template.container_capacity
    ):
        raise ContainerFull
    if (
        container.obj.template.container_max_item_size
        and item.obj.template.size > container.obj.template.container_max_item_size
    ):
        raise ItemTooLarge
    if item.obj.game_object.location != character.obj:
        raise NotInPossession

    item.obj.contained_in = container.obj
    item.obj.save(update_fields=["contained_in"])


@transaction.atomic
def take_out(character: CharacterState, item: ItemState) -> None:
    """Move ``item`` out of its container into ``character``'s possession."""
    item.obj.contained_in = None
    item.obj.save(update_fields=["contained_in"])
    item.obj.game_object.location = character.obj
    item.obj.game_object.save()
```

**Step 5: Commit**

```bash
git commit -am "feat(flows): put_in / take_out container service functions"
```

---

## Task 9: Telnet commands

**Files:**
- Create: `src/commands/inventory.py` (or modify the appropriate existing commands module — search for where `get`/`drop` would naturally live with `Grep` first)
- Test: `src/commands/tests/test_inventory_commands.py`

Skim `src/commands/` first to see how existing commands (movement, etc.) are wired. Match the pattern. Each command:
1. Parses input (`self.args`, `self.lhs`, `self.rhs`).
2. Resolves the item by name in the caller's room/inventory using `caller.search`.
3. Builds states via the appropriate `SceneDataManager` helper.
4. Calls the service function inside a try/except for `InventoryError`, sending `exc.user_message` on failure.
5. Sends a confirmation message on success.

Commands to add:
- `get <item>` — `pick_up`
- `drop <item>` — `drop`
- `give <item> to <person>` — `give`
- `wear <item>` / `wear <item> on <region>` / `wear <item> under <other>` / `wear <item> over <other>` — `equip`
- `remove <item>` — `unequip`
- `put <item> in <container>` — `put_in`
- `take <item> from <container>` — `take_out` (note `get <item> from <container>` already maps to `take_out` — pick whichever syntax the project's existing commands favor, don't introduce both)

Tests should focus on parsing and dispatch, not re-cover the service-function logic. One test per command verifying the right service function is called with the right arguments (use `patch` to stub the service).

The `wear under` / `wear over` parser needs to look up the referenced other-item in the caller's `equipped_slots`, find its slot's region+layer, and pick a layer "below" or "above" it from the wear-target template's available `cached_slots`. If ambiguous (multiple matching layers), fall back to "no clear choice" error.

Commit after each command works, or one commit per command if convenient.

```bash
git commit -m "feat(commands): inventory telnet commands (get/drop/give/wear/remove/put)"
```

---

## Task 10: WebSocket inputfunc

**Files:**
- Modify: `src/server/conf/inputfuncs.py`
- Test: add a test in `src/world/items/tests/test_inventory_services.py` or an inputfunc-specific test file

**Step 1: Write failing test**

The inputfunc dispatches on the `action` kwarg:

```python
class InventoryActionInputfuncTests(TestCase):
    """The `inventory_action` inputfunc dispatches to the right service."""

    @patch("flows.service_functions.inventory.pick_up")
    def test_pick_up_action_dispatches(self, mock_pick_up) -> None:
        from server.conf.inputfuncs import inventory_action
        # Build a fake session with .puppet (the character).
        ...
        inventory_action(session, action="pick_up", item_id=self.item.id)
        mock_pick_up.assert_called_once()
```

**Step 2: Run.** Expected: AttributeError — `inventory_action` not defined.

**Step 3: Implement**

```python
def inventory_action(session, *args, **kwargs):
    """Inbound inventory action from the React client.

    Expected kwargs: action, item_id, plus action-specific extras
    (recipient_id, container_id, region, layer).

    Looks up the item and target by id, builds the appropriate states
    via the session's SceneDataManager, dispatches to the matching
    service function, and sends a CommandError on InventoryError.
    """
    # Implementation: dispatch dict from action name → callable.
    # Build CharacterState + ItemState via the session's scene manager.
    # try: service(...) ; except InventoryError as exc: session.msg(...)
    ...
```

**Step 4: Verify pass.**

**Step 5: Commit**

```bash
git commit -m "feat(server): inventory_action websocket inputfunc"
```

---

## Task 11: Final regression + roadmap update

**Step 1: Full test suite (matches CI's fresh DB)**

```bash
echo "yes" | uv run arx test
```

Without `--keepdb` per the project guideline. Expected: all green. If anything fails, fix root cause — never bypass.

**Step 2: Targeted suites that could be affected**

```bash
echo "yes" | uv run arx test world.items flows commands server --keepdb
```

**Step 3: Update roadmap**

Edit `docs/roadmap/items-equipment.md`. Move "Inventory service functions" from "What's Needed" to "What Exists" (or strike-through with **done**). Note the slice is service-layer-only and that visible-equipment, item stats, and frontend UI are still pending.

```bash
git add docs/roadmap/items-equipment.md
git commit -m "docs(items): mark inventory service functions complete in roadmap"
```

**Step 4: Final review**

```bash
git -C /c/Users/apost/PycharmProjects/arxii log --oneline main..HEAD
```

Should see the commit chain from Task 1 through Task 11. Each commit should pass the suite on its own (clean bisectability).

**Step 5: Open PR**

Manual via the GitHub web interface (per project rule — no `gh`). Title: `feat(items): inventory service functions for pick_up/drop/give/equip/etc.`

PR description should include:
- Link to the design doc
- Note that this is service-layer-only with no migrations
- List the new InventoryError types and where they surface
- Link the natural follow-ups: visible-equipment in `look`, item stats model, frontend inventory panel, crafting integration

---

## Risks and mitigations

- **Stale `cached_slots`** on `ItemTemplate` — we read this in `equip`. We never modify slots from the service layer, so invalidation isn't a concern.
- **Identity-map staleness on character.equipped_items** — if a `cached_property` exists on the character for currently-equipped items, mutations here may leave it stale. If a test fails due to this, update in place per the SharedMemoryModel guidance in CLAUDE.md (don't flush the cache).
- **Telnet parser ambiguity** — `caller.search` already handles "did you mean X or Y" prompts; trust it.
- **Atomicity** — every multi-row mutation is wrapped in `@transaction.atomic`. Tests for `equip` should include a forced failure mid-loop (e.g., patch the second `EquippedItem.objects.create` to raise) and assert no rows persist. Add this if any production bug surfaces a partial-equip state.
