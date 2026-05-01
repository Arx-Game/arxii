# Outfits Phase A Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship savable named Outfits — players can wear, save, edit, and delete looks; outfits are stored in wardrobe items and applied atomically via either the React frontend or telnet.

**Architecture:** Two-layer split established in the inventory PR. Apply/undress are IC actions through the action layer (`ApplyOutfitAction`, `UndressAction`). Save/edit/delete are configuration CRUD via REST (`OutfitViewSet`). `Outfit` model FKs to `CharacterSheet` (never ObjectDB) and to a wardrobe `ItemInstance` (an item with `is_wardrobe=True`). Apply requires the wardrobe to be in reach + every constituent item to be in reach. Frontend renders outfit cards with placeholder regions for future fashion/legendary/mantle/bonus content.

**Tech Stack:** Django 5, DRF, Evennia, FactoryBoy, React 18, shadcn/ui pattern (Radix + Tailwind), Framer Motion, react-query, react-markdown, sonner, openapi-typescript.

**Design source:** `docs/plans/2026-04-30-outfits-phase-a-design.md`

---

## Pre-flight

```bash
git -C /c/Users/apost/PycharmProjects/arxii status
git -C /c/Users/apost/PycharmProjects/arxii branch --show-current
```

Expected: `outfits-phase-a` branch, clean tree (only the design + plan + roadmap docs ahead of main).

Each task ends with a commit. TDD: failing test → run → minimal code → run → commit.

To run tests: `echo "yes" | uv run --directory /c/Users/apost/PycharmProjects/arxii arx test world.items --keepdb -v 2`

To run a specific test: `... arx test world.items.tests.test_outfit_models.OutfitModelTests.test_unique_name_per_character_sheet --keepdb -v 2`

---

## Task 1: Models + migration

**Files:**
- Modify: `src/world/items/constants.py` — no changes (BodyRegion / EquipmentLayer already exist; new constants not needed)
- Modify: `src/world/items/models.py` — add `is_wardrobe` to `ItemTemplate`, add `Outfit` and `OutfitSlot` classes
- Modify: `src/world/items/factories.py` — extend `ItemTemplateFactory` with `is_wardrobe`; add `OutfitFactory`, `OutfitSlotFactory`
- Test: `src/world/items/tests/test_outfit_models.py` (new)
- Migration: generated via `arx manage makemigrations items`

### Step 1: Write the failing test

```python
# src/world/items/tests/test_outfit_models.py
"""Tests for Outfit + OutfitSlot models."""

from django.db import IntegrityError
from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import (
    ItemInstanceFactory,
    ItemTemplateFactory,
    OutfitFactory,
    OutfitSlotFactory,
    TemplateSlotFactory,
)
from world.items.models import Outfit, OutfitSlot


class ItemTemplateWardrobeFlagTests(TestCase):
    def test_default_is_wardrobe_false(self) -> None:
        template = ItemTemplateFactory(name="Plain shirt")
        self.assertFalse(template.is_wardrobe)

    def test_can_be_set_to_true(self) -> None:
        template = ItemTemplateFactory(name="Walnut wardrobe", is_wardrobe=True)
        self.assertTrue(template.is_wardrobe)


class OutfitModelTests(TestCase):
    def setUp(self) -> None:
        self.character = ObjectDBFactory(db_typeclass_path="typeclasses.characters.Character")
        self.sheet = CharacterSheetFactory(character=self.character)
        self.wardrobe_template = ItemTemplateFactory(
            name="Test Wardrobe",
            is_wardrobe=True,
            is_container=True,
        )
        wardrobe_obj = ObjectDBFactory(db_typeclass_path="typeclasses.objects.Object")
        self.wardrobe = ItemInstanceFactory(
            template=self.wardrobe_template,
            game_object=wardrobe_obj,
        )

    def test_can_create_outfit(self) -> None:
        outfit = OutfitFactory(
            character_sheet=self.sheet,
            wardrobe=self.wardrobe,
            name="Court Attire",
        )
        self.assertEqual(outfit.name, "Court Attire")
        self.assertEqual(outfit.character_sheet, self.sheet)
        self.assertEqual(outfit.wardrobe, self.wardrobe)

    def test_unique_name_per_character_sheet(self) -> None:
        OutfitFactory(character_sheet=self.sheet, wardrobe=self.wardrobe, name="Court Attire")
        with self.assertRaises(IntegrityError):
            OutfitFactory(
                character_sheet=self.sheet,
                wardrobe=self.wardrobe,
                name="Court Attire",
            )

    def test_different_characters_can_share_outfit_names(self) -> None:
        other_character = ObjectDBFactory(
            db_key="OtherChar",
            db_typeclass_path="typeclasses.characters.Character",
        )
        other_sheet = CharacterSheetFactory(character=other_character)
        OutfitFactory(character_sheet=self.sheet, wardrobe=self.wardrobe, name="Court Attire")
        OutfitFactory(character_sheet=other_sheet, wardrobe=self.wardrobe, name="Court Attire")
        self.assertEqual(Outfit.objects.filter(name="Court Attire").count(), 2)

    def test_deleting_wardrobe_cascades_outfit(self) -> None:
        OutfitFactory(character_sheet=self.sheet, wardrobe=self.wardrobe, name="Court Attire")
        self.wardrobe.delete()
        self.assertEqual(Outfit.objects.count(), 0)


class OutfitSlotModelTests(TestCase):
    def setUp(self) -> None:
        character = ObjectDBFactory(db_typeclass_path="typeclasses.characters.Character")
        sheet = CharacterSheetFactory(character=character)
        wardrobe_template = ItemTemplateFactory(name="Wardrobe", is_wardrobe=True, is_container=True)
        wardrobe_obj = ObjectDBFactory(db_typeclass_path="typeclasses.objects.Object")
        wardrobe = ItemInstanceFactory(template=wardrobe_template, game_object=wardrobe_obj)
        self.outfit = OutfitFactory(character_sheet=sheet, wardrobe=wardrobe, name="Test")

        self.shirt_template = ItemTemplateFactory(name="Shirt")
        TemplateSlotFactory(
            template=self.shirt_template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        item_obj = ObjectDBFactory(db_typeclass_path="typeclasses.objects.Object")
        self.item = ItemInstanceFactory(template=self.shirt_template, game_object=item_obj)

    def test_can_create_slot(self) -> None:
        slot = OutfitSlotFactory(
            outfit=self.outfit,
            item_instance=self.item,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        self.assertEqual(slot.outfit, self.outfit)
        self.assertEqual(slot.item_instance, self.item)

    def test_unique_per_outfit_region_layer(self) -> None:
        OutfitSlotFactory(
            outfit=self.outfit,
            item_instance=self.item,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        other_obj = ObjectDBFactory(db_typeclass_path="typeclasses.objects.Object")
        other_item = ItemInstanceFactory(template=self.shirt_template, game_object=other_obj)
        with self.assertRaises(IntegrityError):
            OutfitSlotFactory(
                outfit=self.outfit,
                item_instance=other_item,
                body_region=BodyRegion.TORSO,
                equipment_layer=EquipmentLayer.BASE,
            )

    def test_deleting_outfit_cascades_slots(self) -> None:
        OutfitSlotFactory(
            outfit=self.outfit,
            item_instance=self.item,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        self.outfit.delete()
        self.assertEqual(OutfitSlot.objects.count(), 0)

    def test_deleting_item_cascades_slot(self) -> None:
        OutfitSlotFactory(
            outfit=self.outfit,
            item_instance=self.item,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        self.item.delete()
        self.assertEqual(OutfitSlot.objects.count(), 0)
```

### Step 2: Run to verify failure

```bash
echo "yes" | uv run --directory /c/Users/apost/PycharmProjects/arxii arx test world.items.tests.test_outfit_models --keepdb -v 2
```

Expected: ImportError on `OutfitFactory` / `Outfit` / `OutfitSlot`.

### Step 3: Implement models

In `src/world/items/models.py`, add `is_wardrobe` to `ItemTemplate` (with the other boolean flags):

```python
is_wardrobe = models.BooleanField(
    default=False,
    help_text="Whether instances of this template can store Outfit definitions.",
)
```

At the end of the file, add the `Outfit` and `OutfitSlot` models per the design doc. Use `SharedMemoryModel`. Constraints: unique on `(character_sheet, name)` for `Outfit`, unique on `(outfit, body_region, equipment_layer)` for `OutfitSlot`. Both FK chains use `on_delete=CASCADE` per the design.

`Outfit` ordering: `["name"]`.

`OutfitSlot` related_name: `slots` (on Outfit) and `outfit_slots` (on ItemInstance).

### Step 4: Add factories

In `src/world/items/factories.py`, add `is_wardrobe = False` to `ItemTemplateFactory` (default), then:

```python
class OutfitFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Outfit

    name = factory.Sequence(lambda n: f"Outfit {n}")
    description = ""
    # character_sheet and wardrobe must be provided by callers


class OutfitSlotFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = OutfitSlot
    # outfit, item_instance, body_region, equipment_layer required from caller
```

If a `TemplateSlotFactory` doesn't already exist, check `factories.py` first — it's used by existing tests in `test_inventory_services.py`, so it should be there.

### Step 5: Generate migration

```bash
uv run --directory /c/Users/apost/PycharmProjects/arxii arx manage makemigrations items
```

Expected output: `Migrations for 'items': 0004_<auto-name>.py — Create model Outfit, Create model OutfitSlot, Add field is_wardrobe to itemtemplate.`

### Step 6: Run tests

```bash
echo "yes" | uv run --directory /c/Users/apost/PycharmProjects/arxii arx test world.items.tests.test_outfit_models --keepdb -v 2
```

Expected: 9 tests pass.

### Step 7: Commit

```bash
git -C /c/Users/apost/PycharmProjects/arxii add src/world/items/models.py src/world/items/factories.py src/world/items/migrations/ src/world/items/tests/test_outfit_models.py
git -C /c/Users/apost/PycharmProjects/arxii commit -m "feat(items): Outfit and OutfitSlot models with is_wardrobe flag"
```

---

## Task 2: OutfitIncomplete exception + magic naming comment

**Files:**
- Modify: `src/world/items/exceptions.py` — add `OutfitIncomplete`
- Modify: `src/world/items/tests/test_exceptions.py` — add to `INVENTORY_SUBCLASSES` tuple
- Modify: `src/world/magic/services/gain.py` — add clarifying comment near `outfit_daily_trickle_for_character`

### Step 1: Test

Add `OutfitIncomplete` to the `INVENTORY_SUBCLASSES` tuple in `test_exceptions.py`:

```python
from world.items.exceptions import (
    ...,
    OutfitIncomplete,
)

INVENTORY_SUBCLASSES = (
    ...,
    OutfitIncomplete,
)
```

### Step 2: Run, verify ImportError.

### Step 3: Implement

In `src/world/items/exceptions.py`, in the inventory action errors section:

```python
class OutfitIncomplete(InventoryError):
    user_message = "Some pieces of that outfit are missing."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {"Some pieces of that outfit are missing."},
    )
```

In `src/world/magic/services/gain.py`, find the `outfit_daily_trickle_for_character` function and add a comment at the top of its docstring:

```python
"""Issue ResonanceGrant rows for items currently equipped on the character.

Note: "outfit" here refers to the character's *current loadout* (whatever is
worn right now), not the saved Outfit entity in `world.items.models.Outfit`.
The two concepts coexist: a saved Outfit is a named arrangement; the
current loadout is whatever EquippedItem rows exist on the character at
this moment.
"""
```

### Step 4: Run tests, verify pass.

```bash
echo "yes" | uv run --directory /c/Users/apost/PycharmProjects/arxii arx test world.items.tests.test_exceptions --keepdb -v 2
```

### Step 5: Commit

```bash
git -C /c/Users/apost/PycharmProjects/arxii commit -am "feat(items): OutfitIncomplete exception, clarify magic outfit naming"
```

---

## Task 3: OutfitState

**Files:**
- Create: `src/flows/object_states/outfit_state.py`
- Test: `src/world/items/tests/test_outfit_state.py`

### Step 1: Write failing test

```python
"""Tests for OutfitState."""

from unittest.mock import MagicMock

from django.test import TestCase

from flows.object_states.outfit_state import OutfitState
from world.items.factories import (
    ItemInstanceFactory,
    ItemTemplateFactory,
    OutfitFactory,
)
# ... factory imports for character_sheet, ObjectDB, etc.


class OutfitStateDefaultsTests(TestCase):
    """OutfitState wraps an Outfit and exposes can_apply + reachability."""

    @classmethod
    def setUpTestData(cls) -> None:
        # Build character + sheet + wardrobe + outfit (cf. test_outfit_models setUp)
        ...

    def test_can_apply_default_true_with_no_actor(self) -> None:
        state = OutfitState(self.outfit, context=MagicMock())
        self.assertTrue(state.can_apply())

    def test_outfit_property_returns_wrapped_outfit(self) -> None:
        state = OutfitState(self.outfit, context=MagicMock())
        self.assertIs(state.outfit, self.outfit)

    def test_is_reachable_by_delegates_to_wardrobe(self) -> None:
        # Wardrobe in actor's room → reachable
        # Wardrobe in another room → not reachable
        ...
```

### Step 2: Run, verify ImportError.

### Step 3: Implement

```python
"""Object state wrapper for Outfit instances."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from flows.object_states.base_state import BaseState

if TYPE_CHECKING:
    from world.items.models import Outfit


class OutfitState(BaseState):
    """Mutable wrapper for an outfit during a flow run.

    Permission methods default to True. Behavior packages plug in via
    ``_run_package_hook`` to deny actions for cursed/locked outfits.
    """

    @property
    def outfit(self) -> "Outfit":
        """Return the wrapped Outfit, narrowed for type-checkers."""
        return cast("Outfit", self.obj)

    def can_apply(self, actor: BaseState | None = None) -> bool:
        """Whether ``actor`` may apply this outfit."""
        result = self._run_package_hook("can_apply", actor)
        if result is not None:
            return bool(result)
        if actor is None or actor.obj is None:
            return True
        return self.is_reachable_by(actor.obj)

    def is_reachable_by(self, character_obj) -> bool:
        """Whether ``character_obj`` can apply this outfit.

        Delegates to the wardrobe's reachability — the outfit definition
        lives in the wardrobe, so the wardrobe must be in reach.
        """
        from flows.object_states.item_state import ItemState  # noqa: PLC0415 - circular avoidance

        wardrobe_state = ItemState(self.outfit.wardrobe, context=self.context)
        return wardrobe_state.is_reachable_by(character_obj)
```

### Step 4: Run, verify pass.

### Step 5: Commit

```bash
git -C /c/Users/apost/PycharmProjects/arxii commit -am "feat(flows): OutfitState wrapper with can_apply + is_reachable_by"
```

---

## Task 4: apply_outfit + undress services

**Files:**
- Create: `src/flows/service_functions/outfits.py`
- Test: `src/world/items/tests/test_outfit_services.py`

### Step 1: Write failing tests

Create `test_outfit_services.py` with `ApplyOutfitTests` and `UndressTests`:

`ApplyOutfitTests`:
- `test_apply_equips_all_slots` — outfit with 2 slots, no current loadout → after apply, both EquippedItem rows exist
- `test_apply_swaps_conflicting_slot` — actor wearing different shirt → after apply, only the outfit's shirt remains
- `test_apply_leaves_unrelated_slots_alone` — actor wearing necklace at neck/accessory, outfit only specifies torso → necklace stays after apply
- `test_apply_rejects_when_wardrobe_not_in_reach` — wardrobe in another room → `NotReachable`
- `test_apply_rejects_when_item_not_in_reach` — outfit slot's item is in another character's inventory → `NotReachable`
- `test_apply_rejects_outfit_belonging_to_different_character` — outfit.character_sheet != actor's sheet → `PermissionDenied`
- `test_apply_with_missing_pieces_succeeds_partially` — one slot's item was deleted (cascade left fewer slots) → still applies remaining slots, no error

`UndressTests`:
- `test_undress_removes_all_equipped_items` — actor wearing 3 items → 0 EquippedItem rows after
- `test_undress_idempotent_when_naked` — actor wearing 0 → undress succeeds, no error
- `test_undress_keeps_items_in_inventory` — items' game_object.location stays at character

### Step 2: Run, expect ImportError.

### Step 3: Implement

```python
"""Outfit-related service functions."""

from __future__ import annotations

from django.db import transaction

from flows.object_states.character_state import CharacterState
from flows.object_states.outfit_state import OutfitState
from flows.service_functions.inventory import equip, unequip
from world.items.exceptions import NotReachable, PermissionDenied


@transaction.atomic
def apply_outfit(character: CharacterState, outfit_state: OutfitState) -> None:
    """Equip all of ``outfit_state``'s pieces atomically.

    Slots not specified by the outfit are left as-is (no clean-strip).
    Items already equipped at the same (region, layer) are auto-swapped
    via the existing equip policy.
    """
    outfit = outfit_state.outfit
    if outfit.character_sheet.character != character.obj:
        raise PermissionDenied
    if not outfit_state.can_apply(actor=character):
        raise NotReachable

    from flows.object_states.item_state import ItemState  # noqa: PLC0415

    for slot in outfit.slots.all():
        item_state = ItemState(slot.item_instance, context=character.context)
        if not item_state.is_reachable_by(character.obj):
            raise NotReachable
        # equip() handles auto-swap + multi-region atomicity inside the
        # outer transaction.
        equip(character, item_state)


@transaction.atomic
def undress(character: CharacterState) -> None:
    """Unequip every item currently worn by the character.

    Items stay in inventory (the existing unequip behavior). Idempotent
    on a naked character.
    """
    from flows.object_states.item_state import ItemState  # noqa: PLC0415
    from world.items.models import EquippedItem, ItemInstance  # noqa: PLC0415

    item_ids = (
        EquippedItem.objects.filter(character=character.obj)
        .values_list("item_instance_id", flat=True)
        .distinct()
    )
    for item in ItemInstance.objects.filter(id__in=list(item_ids)):
        item_state = ItemState(item, context=character.context)
        unequip(character, item_state)
```

### Step 4: Run, verify pass.

### Step 5: Commit

```bash
git -C /c/Users/apost/PycharmProjects/arxii commit -am "feat(flows): apply_outfit + undress service functions"
```

---

## Task 5: CRUD service functions (save / delete / add_slot / remove_slot)

**Files:**
- Modify: `src/flows/service_functions/outfits.py` — add the four CRUD service functions
- Modify: `src/world/items/tests/test_outfit_services.py` — add `SaveOutfitTests`, `DeleteOutfitTests`, `OutfitSlotEditTests`

### Step 1: Tests

For each service:

`SaveOutfitTests`:
- `test_save_creates_outfit_with_current_loadout` — actor wearing 2 items at the wardrobe → save → new Outfit with 2 OutfitSlot rows mirroring the EquippedItem rows
- `test_save_with_naked_character_creates_empty_outfit` — actor naked → save → Outfit with 0 slots
- `test_save_rejects_when_wardrobe_not_in_reach` — wardrobe in another room → `NotReachable`
- `test_save_rejects_when_template_not_wardrobe` — passed an item with `is_wardrobe=False` → `NotAContainer` (or new exception?)
- `test_save_unique_name_per_character_sheet` — already have an outfit named "X" → save another with "X" → IntegrityError

`DeleteOutfitTests`:
- `test_delete_removes_outfit_and_slots` — outfit with 2 slots → delete → outfit and OutfitSlot rows gone
- `test_delete_does_not_touch_items` — delete outfit → ItemInstance rows still exist

`OutfitSlotEditTests`:
- `test_add_slot_creates_row` — empty outfit + add_outfit_slot → 1 row
- `test_add_slot_replaces_existing` — outfit has slot at torso/base → add_outfit_slot at torso/base with different item → only the new item's slot remains
- `test_add_slot_rejects_template_incompatible` — item template doesn't declare (region, layer) → `SlotIncompatible`
- `test_remove_slot_deletes_row` — outfit has slot → remove_outfit_slot → 0 rows
- `test_remove_slot_idempotent` — outfit has no slot at (region, layer) → remove → no error

### Step 2: Run, expect failures.

### Step 3: Implement

Add to `outfits.py`:

```python
def save_outfit(
    *,
    character_sheet,
    wardrobe,
    name: str,
    description: str = "",
):
    """Snapshot the character's currently-equipped items into a new Outfit."""
    from world.items.exceptions import NotAContainer  # noqa: PLC0415
    from world.items.models import EquippedItem, Outfit, OutfitSlot  # noqa: PLC0415

    if not wardrobe.template.is_wardrobe:
        raise NotAContainer
    # Reach validation happens at the REST/serializer level (since this
    # service is called from REST, not from a CharacterState wrapper).

    with transaction.atomic():
        outfit = Outfit.objects.create(
            character_sheet=character_sheet,
            wardrobe=wardrobe,
            name=name,
            description=description,
        )
        rows = EquippedItem.objects.filter(character=character_sheet.character)
        OutfitSlot.objects.bulk_create([
            OutfitSlot(
                outfit=outfit,
                item_instance=row.item_instance,
                body_region=row.body_region,
                equipment_layer=row.equipment_layer,
            )
            for row in rows
        ])
    return outfit


def delete_outfit(outfit) -> None:
    """Delete the outfit definition. Items are not touched."""
    outfit.delete()


@transaction.atomic
def add_outfit_slot(*, outfit, item_instance, body_region, equipment_layer):
    """Add or replace a slot in an outfit."""
    from world.items.exceptions import SlotIncompatible  # noqa: PLC0415
    from world.items.models import OutfitSlot  # noqa: PLC0415

    template_slots = item_instance.template.cached_slots
    if not any(
        s.body_region == body_region and s.equipment_layer == equipment_layer
        for s in template_slots
    ):
        raise SlotIncompatible

    OutfitSlot.objects.filter(
        outfit=outfit,
        body_region=body_region,
        equipment_layer=equipment_layer,
    ).delete()
    return OutfitSlot.objects.create(
        outfit=outfit,
        item_instance=item_instance,
        body_region=body_region,
        equipment_layer=equipment_layer,
    )


@transaction.atomic
def remove_outfit_slot(*, outfit, body_region, equipment_layer) -> None:
    from world.items.models import OutfitSlot  # noqa: PLC0415

    OutfitSlot.objects.filter(
        outfit=outfit,
        body_region=body_region,
        equipment_layer=equipment_layer,
    ).delete()
```

### Step 4: Run, verify pass.

### Step 5: Commit

```bash
git -C /c/Users/apost/PycharmProjects/arxii commit -am "feat(flows): save/delete/add-slot/remove-slot outfit services"
```

---

## Task 6: ApplyOutfitAction + UndressAction

**Files:**
- Create: `src/actions/definitions/outfits.py`
- Modify: `src/actions/registry.py` — register both actions
- Modify: `src/actions/tests/test_base.py` — add `apply_outfit` and `undress` to expected-action assertion
- Test: `src/actions/tests/test_outfit_actions.py` (new)

### Step 1: Write tests

`ApplyOutfitActionTests`:
- `test_apply_outfit_dispatches_service` — happy path
- `test_apply_outfit_unknown_outfit_id_returns_failure` — invalid pk → `ActionResult(success=False)`
- `test_apply_outfit_inventory_error_surfaces_user_message` — service raises `NotReachable` → ActionResult contains user_message

`UndressActionTests`:
- `test_undress_dispatches_service` — happy path

### Step 2: Run, expect ImportError.

### Step 3: Implement

```python
# src/actions/definitions/outfits.py
"""Outfit-related actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionContext, ActionResult, TargetType
from flows.object_states.outfit_state import OutfitState
from flows.scene_data_manager import SceneDataManager
from flows.service_functions.communication import message_location
from flows.service_functions.outfits import apply_outfit, undress
from world.items.exceptions import InventoryError

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


@dataclass
class ApplyOutfitAction(Action):
    key: str = "apply_outfit"
    name: str = "Wear Outfit"
    icon: str = "wardrobe"
    category: str = "items"
    target_type: TargetType = TargetType.SINGLE

    intent_event: str | None = "before_apply_outfit"
    result_event: str | None = "apply_outfit"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.items.models import Outfit  # noqa: PLC0415

        outfit_id = kwargs.get("outfit_id")
        if outfit_id is None:
            return ActionResult(success=False, message="Wear which outfit?")
        try:
            outfit = Outfit.objects.get(pk=outfit_id)
        except Outfit.DoesNotExist:
            return ActionResult(success=False, message="That outfit no longer exists.")

        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        outfit_state = OutfitState(outfit, context=sdm)

        try:
            apply_outfit(actor_state, outfit_state)
        except InventoryError as exc:
            return ActionResult(success=False, message=exc.user_message)

        message_location(
            actor_state,
            "$You() $conj(change) into {outfit}.",
            mapping={"outfit": outfit.name},
        )
        return ActionResult(success=True)


@dataclass
class UndressAction(Action):
    key: str = "undress"
    name: str = "Undress"
    icon: str = "shirt-off"
    category: str = "items"
    target_type: TargetType = TargetType.SELF

    intent_event: str | None = "before_undress"
    result_event: str | None = "undress"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)

        try:
            undress(actor_state)
        except InventoryError as exc:
            return ActionResult(success=False, message=exc.user_message)

        message_location(actor_state, "$You() $conj(undress).")
        return ActionResult(success=True)
```

Update `actions/registry.py`:

```python
from actions.definitions.outfits import ApplyOutfitAction, UndressAction
# ...
_ALL_ACTIONS: list[Action] = [
    ...,
    ApplyOutfitAction(),
    UndressAction(),
]
```

Update `actions/tests/test_base.py` to include `apply_outfit` and `undress` in the expected-keys assertion.

### Step 4: Run, verify pass.

### Step 5: Commit

```bash
git -C /c/Users/apost/PycharmProjects/arxii commit -am "feat(actions): ApplyOutfitAction + UndressAction registered"
```

---

## Task 7: Telnet commands (undress + extend CmdWear)

**Files:**
- Modify: `src/commands/evennia_overrides/items.py` — add `CmdUndress`, extend `CmdWear`
- Modify: `src/commands/default_cmdsets.py` — register `CmdUndress`
- Test: `src/commands/tests/test_dispatchers.py` — add `CmdUndressTests`, extend `CmdWearTests`

### Step 1: Tests

```python
class CmdUndressTests(TestCase):
    def test_undress_dispatches_undress_action(self):
        cmd = _make_cmd(CmdUndress, args="")
        ...

class CmdWearTests:
    def test_wear_outfit_name_dispatches_apply_outfit(self):
        # Pre-create outfit
        # Run "wear outfit Court Attire"
        # Assert self.action == ApplyOutfitAction
        # Assert kwargs == {"outfit_id": outfit.pk}

    def test_wear_outfit_unknown_name_raises_command_error(self):
        # ...

    def test_wear_item_unchanged(self):
        # Existing wear-item path still works
```

### Step 2: Run, expect failures.

### Step 3: Implement

In `items.py`:

```python
class CmdUndress(ArxCommand):
    """Remove all worn items at once. They go back to your inventory."""

    key = "undress"
    locks = "cmd:all()"
    action = UndressAction()

    def resolve_action_args(self) -> dict[str, Any]:
        return {}
```

Extend `CmdWear.resolve_action_args` (currently in `items.py`):

```python
def resolve_action_args(self) -> dict[str, Any]:
    args = self.require_args("Wear what?")
    outfit_match = re.match(r"^outfit\s+(.+)$", args, flags=re.IGNORECASE)
    if outfit_match:
        outfit_name = outfit_match.group(1).strip()
        sheet = self.caller.sheet_data
        outfit = Outfit.objects.filter(
            character_sheet=sheet,
            name__iexact=outfit_name,
        ).first()
        if outfit is None:
            raise CommandError(f"You have no outfit named '{outfit_name}'.")
        self.action = ApplyOutfitAction()
        return {"outfit_id": outfit.pk}
    # Existing wear-item path
    return {"target": self.search_or_raise(args, location=self.caller)}
```

Add imports for `Outfit`, `ApplyOutfitAction`, `UndressAction`, `re`.

Register `CmdUndress` in `default_cmdsets.py`'s `CharacterCmdSet`.

### Step 4: Run, verify pass.

### Step 5: Commit

```bash
git -C /c/Users/apost/PycharmProjects/arxii commit -am "feat(commands): undress command + 'wear outfit <name>' fork in CmdWear"
```

---

## Task 8: ItemInstanceViewSet (read-only carried items)

**Files:**
- Modify: `src/world/items/views.py` — add `ItemInstanceViewSet`
- Modify: `src/world/items/serializers.py` — add `ItemInstanceReadSerializer`
- Modify: `src/world/items/filters.py` — add `ItemInstanceFilter` with `character` filter
- Modify: `src/world/items/urls.py` — register
- Test: `src/world/items/tests/test_item_instance_views.py` (new)

### Step 1: Tests

- `test_list_filters_by_character` — only items where `game_object.location == requested character` returned
- `test_list_excludes_other_characters_inventory` — items on other characters not returned
- `test_list_unauthenticated_returns_401`
- `test_list_authorized_for_currently_played_character`
- `test_list_includes_template_and_quality_data` — read serializer includes nested template + quality_tier

### Step 2: Run, expect failures.

### Step 3: Implement

`ItemInstanceFilter`:

```python
class ItemInstanceFilter(django_filters.FilterSet):
    character = django_filters.NumberFilter(field_name="game_object__location__id")

    class Meta:
        model = ItemInstance
        fields = ["character"]
```

`ItemInstanceReadSerializer` — minimal fields needed by the wardrobe page: id, display_name, display_description, quality_tier (nested), template (nested with name, weight, size, value, image_url), display_image_url, contained_in (id), facets (slim list).

`ItemInstanceViewSet`:

```python
class ItemInstanceViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only listing of item instances. Filter by character to get a
    character's carried inventory."""

    permission_classes = [IsAuthenticated]
    serializer_class = ItemInstanceReadSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = ItemInstanceFilter
    pagination_class = ItemTemplatePagination
    queryset = ItemInstance.objects.select_related(
        "template",
        "quality_tier",
        "game_object",
    ).prefetch_related(
        Prefetch(
            "item_facets",
            queryset=ItemFacet.objects.select_related("facet", "attachment_quality_tier"),
            to_attr="cached_item_facets",
        ),
    )
```

Register in `urls.py`.

### Step 4: Run, verify pass.

### Step 5: Commit

```bash
git -C /c/Users/apost/PycharmProjects/arxii commit -am "feat(items): ItemInstanceViewSet read-only carried-items endpoint"
```

---

## Task 9: OutfitViewSet REST CRUD

**Files:**
- Modify: `src/world/items/views.py` — add `OutfitViewSet`, `OutfitWritePermission`
- Modify: `src/world/items/serializers.py` — add `OutfitReadSerializer`, `OutfitWriteSerializer`, `OutfitSlotSerializer`
- Modify: `src/world/items/filters.py` — add `OutfitFilter`
- Modify: `src/world/items/urls.py` — register
- Test: `src/world/items/tests/test_outfit_views.py` (new)

### Step 1: Tests

CRUD coverage:
- `test_list_returns_own_outfits` — current player's outfits
- `test_retrieve_returns_outfit_with_slots`
- `test_create_calls_save_outfit_service` — POST creates outfit, snapshots current loadout
- `test_create_rejects_non_wardrobe_template` — wardrobe id is a non-wardrobe item → 400
- `test_create_rejects_when_not_playing_character` — 403
- `test_partial_update_can_rename` — PATCH name
- `test_destroy_calls_delete_outfit_service`
- `test_destroy_does_not_touch_items` — items still exist after outfit delete
- `test_unauthenticated_returns_401`

### Step 2: Run, expect failures.

### Step 3: Implement

Permission class mirrors `EquippedItemWritePermission` from prior PR:

```python
class OutfitWritePermission(IsAuthenticated):
    """Allow CRUD only when request.user currently plays the character_sheet."""

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if request.method in SAFE_METHODS or request.user.is_staff:
            return True
        if request.method != "POST":
            return True  # delegated to has_object_permission
        sheet_pk = request.data.get("character_sheet")
        if sheet_pk is None:
            return True  # serializer rejects
        try:
            sheet = CharacterSheet.objects.get(pk=sheet_pk)
        except CharacterSheet.DoesNotExist:
            return True
        return _account_currently_plays(request.user, sheet)

    def has_object_permission(self, request, view, obj: Outfit):
        if request.user.is_staff:
            return True
        return _account_currently_plays(request.user, obj.character_sheet)
```

`OutfitWriteSerializer.create` calls `save_outfit` (or builds the outfit + slots by calling EquippedItem snapshot logic). `update` allows name/description edits. `destroy` calls `delete_outfit`.

`OutfitFilter`:

```python
class OutfitFilter(django_filters.FilterSet):
    character_sheet = django_filters.NumberFilter(field_name="character_sheet__id")
    wardrobe = django_filters.NumberFilter(field_name="wardrobe__id")

    class Meta:
        model = Outfit
        fields = ["character_sheet", "wardrobe"]
```

`ViewSet`:

```python
class OutfitViewSet(viewsets.ModelViewSet):
    permission_classes = [OutfitWritePermission]
    pagination_class = ItemTemplatePagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = OutfitFilter
    queryset = Outfit.objects.select_related(
        "character_sheet", "wardrobe", "wardrobe__template",
    ).prefetch_related(
        Prefetch(
            "slots",
            queryset=OutfitSlot.objects.select_related(
                "item_instance", "item_instance__template", "item_instance__quality_tier",
            ),
            to_attr="cached_slots",
        ),
    )

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return OutfitWriteSerializer
        return OutfitReadSerializer

    def perform_destroy(self, instance):
        delete_outfit(instance)
```

Register in `urls.py`.

### Step 4: Run, verify pass.

### Step 5: Commit

```bash
git -C /c/Users/apost/PycharmProjects/arxii commit -am "feat(items): OutfitViewSet REST CRUD with character-played permission"
```

---

## Task 10: Frontend feature folder + types + API client

**Files:**
- Create: `frontend/src/inventory/api.ts`
- Create: `frontend/src/inventory/types.ts`
- Create: `frontend/src/inventory/hooks/useOutfits.ts`
- Create: `frontend/src/inventory/hooks/useInventory.ts`
- Create: `frontend/src/inventory/index.ts`
- Run: `just gen-api-types` to regenerate `frontend/src/generated/api.d.ts`

### Step 1: Generate API types

```bash
cd /c/Users/apost/PycharmProjects/arxii && just gen-api-types
```

Expected: `frontend/src/generated/api.d.ts` updated with `/api/items/outfits/`, `/api/items/inventory/`, etc.

### Step 2: Write API client wrappers

Mirror `frontend/src/codex/api.ts` style. Functions: `listOutfits(characterSheetId)`, `getOutfit(id)`, `createOutfit(payload)`, `updateOutfit(id, payload)`, `deleteOutfit(id)`, `listInventory(characterId)`, `listEquipped(characterId)`.

### Step 3: Write react-query hooks

`useOutfits(characterSheetId)`, `useOutfit(id)`, `useCreateOutfit()`, `useUpdateOutfit()`, `useDeleteOutfit()`, `useInventory(characterId)`, `useEquippedItems(characterId)`.

### Step 4: Add a stub WardrobePage

Just a placeholder that renders "Wardrobe" — so we can wire up the route in the next task without scope blow-up.

### Step 5: Add page route

In whatever does route registration (likely `App.tsx` or similar — check the existing pages to find the pattern).

### Step 6: Commit

```bash
git -C /c/Users/apost/PycharmProjects/arxii commit -am "feat(frontend): inventory feature folder scaffolding + API hooks"
```

---

## Task 11: Frontend components — PaperDoll, ItemCard, OutfitCard, ItemDetailPanel

**Files:**
- Create: `frontend/src/inventory/components/PaperDoll.tsx`
- Create: `frontend/src/inventory/components/ItemCard.tsx`
- Create: `frontend/src/inventory/components/OutfitCard.tsx`
- Create: `frontend/src/inventory/components/ItemDetailPanel.tsx`
- Create: vitest test files alongside each

### Step 1–5: For each component

Follow shadcn/ui pattern. Use Tailwind. Use `clsx`/`tailwind-merge` for class composition.

`PaperDoll.tsx` — body silhouette with slot indicators. SVG-based; one slot per `BodyRegion`. Click a slot to filter the item list to compatible templates. Empty slot shows ghost outline; occupied slot shows item thumbnail with quality tier border color.

`ItemCard.tsx` — compact row: thumbnail, name (with quality tier color in name or border), small badges for facets. Click → opens `ItemDetailPanel` via parent state.

`OutfitCard.tsx` — per the design doc visual:
- Name, kebab menu (rename / delete)
- Up to 5 item thumbnails, "+N" badge
- Placeholder regions for fashion / legendary / mantle / bonuses (visible in DOM with `data-placeholder` attribute, hidden visually until they have content)
- "Wear" button (primary), "Edit" button (secondary)

`ItemDetailPanel.tsx` — side drawer using Radix `Dialog` or shadcn `Sheet`. Animated via `framer-motion`. Renders:
- Large image
- Markdown description via `react-markdown` + `remark-gfm`
- Quality tier color accent bar
- Facet chips
- Weight/size/value
- Action buttons (Wear / Drop / Give → opens character picker / Put in → opens container picker / Take out)

Each component gets a focused vitest test:
- Renders without crashing
- Click handlers fire
- Conditional rendering (empty states, missing pieces)

### Step 6: Commit each component (or batch as one commit)

```bash
git -C /c/Users/apost/PycharmProjects/arxii commit -am "feat(frontend): PaperDoll, ItemCard, OutfitCard, ItemDetailPanel components"
```

---

## Task 12: Frontend dialogs (Save / Edit / Delete outfit)

**Files:**
- Create: `frontend/src/inventory/components/SaveOutfitDialog.tsx`
- Create: `frontend/src/inventory/components/EditOutfitDialog.tsx`
- Create: `frontend/src/inventory/components/DeleteOutfitDialog.tsx`
- vitest tests

### Implementation notes

`SaveOutfitDialog`:
- Inputs: name (required, unique per character), description (optional, markdown).
- Wardrobe picker — shows reachable wardrobes (from inventory + same room). Defaults to nearest.
- Submit → mutation via `useCreateOutfit()`.
- Toast on success/failure via `sonner`.

`EditOutfitDialog`:
- Lists current slots with a remove button per slot.
- "+ Add piece" — shows a picker filtered to items the character has + region/layer selector.
- Each slot edit calls a flat `/api/items/outfit-slots/` endpoint (which we should add in Task 9 as a separate viewset, OR fold into `OutfitSlot` lifecycle hooks on the OutfitWriteSerializer).
- Or — simpler: the dialog accumulates changes and submits a single PATCH with the full slot list, server-side reconciles. (Easier API for the frontend; more work on the serializer.)
- **Decide before implementing**: pick whichever approach fits Task 9's serializer shape.

`DeleteOutfitDialog`:
- Confirmation modal.
- Submit → `useDeleteOutfit()` mutation.

### Commit

```bash
git -C /c/Users/apost/PycharmProjects/arxii commit -am "feat(frontend): outfit save/edit/delete dialogs"
```

---

## Task 13: WardrobePage assembly + WS subscription

**Files:**
- Modify: `frontend/src/inventory/pages/WardrobePage.tsx` — replace stub with real layout
- Add: integration with WS `action_result` subscription (find existing subscription helper in `frontend/src/`)

### Implementation

Layout per the design doc — outfit grid, paper doll, currently-worn list, all-items grid, detail panel slot.

Wire up:
- Click outfit card → opens outfit detail drawer
- Click item card → opens item detail drawer
- "Wear" on outfit card → fires WS `execute_action({action: "apply_outfit", kwargs: {outfit_id}})`
- "Undress" button in worn panel → fires WS `execute_action({action: "undress"})`. Confirmation modal if 3+ items worn.
- Subscribe to `action_result` WS messages → on success, invalidate the relevant react-query keys (equipped + inventory) so the UI refetches.

### Commit

```bash
git -C /c/Users/apost/PycharmProjects/arxii commit -am "feat(frontend): WardrobePage assembly with WS action_result subscription"
```

---

## Task 14: Final regression + roadmap update

### Step 1: Targeted regression

```bash
echo "yes" | uv run --directory /c/Users/apost/PycharmProjects/arxii arx test world.items actions commands flows --keepdb
```

Plus:

```bash
echo "yes" | uv run --directory /c/Users/apost/PycharmProjects/arxii arx test world --keepdb
```

Plus frontend:

```bash
cd /c/Users/apost/PycharmProjects/arxii/frontend && pnpm typecheck && pnpm lint && pnpm test
```

### Step 2: Update roadmap

Edit `docs/roadmap/items-equipment.md` — add a "Outfits Phase A (DONE)" section listing what shipped. Note Phase B (Fashion), Phase C (Modeling), Phase D (Legendary + Mantle) as future work.

### Step 3: Commit

```bash
git -C /c/Users/apost/PycharmProjects/arxii commit -am "docs(items): mark Outfits Phase A complete in roadmap"
```

### Step 4: Push and open PR

```bash
git -C /c/Users/apost/PycharmProjects/arxii push -u origin outfits-phase-a
```

PR title: `Outfits Phase A — saved looks, apply/undress, REST CRUD, frontend wardrobe`

---

## Risks and mitigations

- **Frontend scope creep.** Tasks 10–13 are the largest chunk and easiest to over-engineer. Mitigation: stay close to existing patterns in `frontend/src/codex/`. Defer drag-to-equip to a follow-up.
- **WS action_result subscription not previously exercised at this depth.** Mitigation: search `frontend/src/` for existing `action_result` consumers — if none, the wardrobe page is the first; add a small subscription helper if needed.
- **`OutfitSlot` edit endpoint shape.** Tasks 9 and 12 should agree on whether slot edits go through a flat viewset or a PATCH-with-full-list pattern. Decide in Task 9; reflect in Task 12.
- **Reach checks during save (REST path).** The REST `OutfitWriteSerializer.create` needs to validate wardrobe reach without a `CharacterState` wrapper available. Use `ItemState(wardrobe, context=SceneDataManager()).is_reachable_by(request.user.puppeted_character)`. If that pattern feels awkward, consider exposing a free function `is_reachable_by(item_instance, character_obj)` in `world.items.helpers` that doesn't need a context.
- **Telnet `wear outfit` collision with `wear <item named "outfit X">`.** Players can name items "outfit". Mitigation: the `outfit ` prefix is checked against the actual `Outfit` table — if no outfit by that name exists, fall through to the wear-item path.

## Out-of-scope follow-ups

- Drag-to-equip individual items
- Phase B (Fashion), Phase C (Modeling), Phase D (Legendary + Mantle)
- Servant retrieval (rooms-and-estates roadmap)
- Outfit sharing / cross-character viewing
