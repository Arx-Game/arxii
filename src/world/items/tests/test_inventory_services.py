"""Tests for inventory mutation service functions."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    ObjectDBFactory,
)
from flows.object_states.character_state import CharacterState
from flows.object_states.item_state import ItemState
from flows.service_functions.inventory import drop, equip, give, pick_up, unequip
from world.character_sheets.factories import CharacterSheetFactory
from world.items.constants import BodyRegion, EquipmentLayer, OwnershipEventType
from world.items.exceptions import NotEquipped, PermissionDenied
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory, TemplateSlotFactory
from world.items.models import EquippedItem, OwnershipEvent
from world.items.services import equip_item


class PickUpTests(TestCase):
    """Cover the four behaviors of ``pick_up``."""

    def setUp(self) -> None:
        # Evennia typeclass instances cannot live on ``setUpTestData`` because
        # Django's per-test deepcopy of class data fails on DbHolder objects.
        self.account = AccountFactory()
        self.room = ObjectDBFactory(
            db_key="PickUpTestRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.character = CharacterFactory(
            db_key="PickUpTestChar",
            location=self.room,
        )
        self.character.db_account = self.account
        self.character.save()

        # Build an ObjectDB for the item, place it in the room, then bind it
        # to a fresh ItemInstance.
        item_obj = ObjectDBFactory(
            db_key="PickUpTestItemObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        item_obj.location = self.room
        item_obj.save()
        self.item = ItemInstanceFactory(game_object=item_obj)

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
        other_account = AccountFactory(username="other_owner")
        self.item.owner = other_account
        self.item.save()
        pick_up(self.character_state, self.item_state)
        self.item.refresh_from_db()
        self.assertEqual(self.item.owner, other_account)

    def test_pickup_denied_by_can_take_raises(self) -> None:
        with patch.object(ItemState, "can_take", return_value=False):
            with self.assertRaises(PermissionDenied):
                pick_up(self.character_state, self.item_state)


class DropTests(TestCase):
    """Cover the three behaviors of ``drop``."""

    def setUp(self) -> None:
        # Same per-test setUp pattern as PickUpTests — DbHolder isn't
        # deepcopy-safe, so setUpTestData breaks for Evennia typeclasses.
        self.account = AccountFactory()
        self.room = ObjectDBFactory(
            db_key="DropTestRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.character = CharacterFactory(
            db_key="DropTestChar",
            location=self.room,
        )
        self.character.db_account = self.account
        self.character.save()

        # Item starts in the character's possession (location=character).
        item_obj = ObjectDBFactory(
            db_key="DropTestItemObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        item_obj.location = self.character
        item_obj.save()
        self.item = ItemInstanceFactory(game_object=item_obj)

        ctx = MagicMock()
        self.character_state = CharacterState(self.character, context=ctx)
        self.item_state = ItemState(self.item, context=ctx)

    def test_drop_moves_item_to_character_location(self) -> None:
        drop(self.character_state, self.item_state)
        self.item.game_object.refresh_from_db()
        self.assertEqual(self.item.game_object.location, self.room)

    def test_drop_auto_unequips_first(self) -> None:
        EquippedItem.objects.create(
            character=self.character,
            item_instance=self.item,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        drop(self.character_state, self.item_state)
        self.assertFalse(EquippedItem.objects.filter(item_instance=self.item).exists())
        self.item.game_object.refresh_from_db()
        self.assertEqual(self.item.game_object.location, self.room)

    def test_drop_denied_raises(self) -> None:
        with patch.object(ItemState, "can_drop", return_value=False):
            with self.assertRaises(PermissionDenied):
                drop(self.character_state, self.item_state)


class GiveTests(TestCase):
    """Cover the three behaviors of ``give``."""

    def setUp(self) -> None:
        # Same per-test setUp pattern as the other test classes.
        self.giver_account = AccountFactory(username="giver_account")
        self.recipient_account = AccountFactory(username="recipient_account")
        self.room = ObjectDBFactory(
            db_key="GiveTestRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.giver = CharacterFactory(
            db_key="GiveTestGiver",
            location=self.room,
        )
        self.giver.db_account = self.giver_account
        self.giver.save()
        self.recipient = CharacterFactory(
            db_key="GiveTestRecipient",
            location=self.room,
        )
        self.recipient.db_account = self.recipient_account
        self.recipient.save()

        # Item starts in the giver's possession, owned by the giver's account.
        item_obj = ObjectDBFactory(
            db_key="GiveTestItemObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        item_obj.location = self.giver
        item_obj.save()
        self.item = ItemInstanceFactory(game_object=item_obj, owner=self.giver_account)

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
        give(self.giver_state, self.recipient_state, self.item_state)
        event = OwnershipEvent.objects.get(item_instance=self.item)
        self.assertEqual(event.event_type, OwnershipEventType.GIVEN)
        self.assertEqual(event.from_account, self.giver_account)
        self.assertEqual(event.to_account, self.recipient_account)

    def test_give_auto_unequips_first(self) -> None:
        EquippedItem.objects.create(
            character=self.giver,
            item_instance=self.item,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        give(self.giver_state, self.recipient_state, self.item_state)
        self.assertFalse(EquippedItem.objects.filter(item_instance=self.item).exists())
        self.item.game_object.refresh_from_db()
        self.assertEqual(self.item.game_object.location, self.recipient)

    def test_give_denied_raises(self) -> None:
        with patch.object(ItemState, "can_give", return_value=False):
            with self.assertRaises(PermissionDenied):
                give(self.giver_state, self.recipient_state, self.item_state)


class EquipTests(TestCase):
    """Cover the five behaviors of ``equip``."""

    def setUp(self) -> None:
        # Same per-test setUp pattern — DbHolder isn't deepcopy-safe, so
        # setUpTestData breaks for Evennia typeclasses.
        self.account = AccountFactory()
        self.room = ObjectDBFactory(
            db_key="EquipTestRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.character = CharacterFactory(
            db_key="EquipTestChar",
            location=self.room,
        )
        self.character.db_account = self.account
        self.character.save()
        self.sheet = CharacterSheetFactory(character=self.character)

        # Single TORSO/BASE slot template.
        self.template = ItemTemplateFactory(name="Equip Test Shirt")
        TemplateSlotFactory(
            template=self.template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        item_obj = ObjectDBFactory(
            db_key="EquipTestItemObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        item_obj.location = self.character
        item_obj.save()
        self.item = ItemInstanceFactory(template=self.template, game_object=item_obj)

        ctx = MagicMock()
        self.character_state = CharacterState(self.character, context=ctx)
        self.item_state = ItemState(self.item, context=ctx)

    def test_equip_into_empty_slot_creates_row(self) -> None:
        equip(self.character_state, self.item_state)
        self.assertTrue(
            EquippedItem.objects.filter(character=self.character, item_instance=self.item).exists()
        )

    def test_equip_same_layer_swaps_existing(self) -> None:
        # Pre-equip a different item in TORSO/BASE.
        existing_obj = ObjectDBFactory(
            db_key="EquipTestExistingObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        existing_obj.location = self.character
        existing_obj.save()
        existing_item = ItemInstanceFactory(template=self.template, game_object=existing_obj)
        equip_item(
            character_sheet=self.sheet,
            item_instance=existing_item,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )

        equip(self.character_state, self.item_state)

        equipped = EquippedItem.objects.filter(character=self.character)
        self.assertEqual(equipped.count(), 1)
        self.assertEqual(equipped.first().item_instance, self.item)

    def test_equip_different_layer_at_same_region_keeps_both(self) -> None:
        # Build a template at TORSO/OUTER, equip it.
        outer_template = ItemTemplateFactory(name="Equip Test Coat")
        TemplateSlotFactory(
            template=outer_template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.OUTER,
        )
        outer_obj = ObjectDBFactory(
            db_key="EquipTestOuterObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        outer_obj.location = self.character
        outer_obj.save()
        outer_item = ItemInstanceFactory(template=outer_template, game_object=outer_obj)
        equip_item(
            character_sheet=self.sheet,
            item_instance=outer_item,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.OUTER,
        )

        # Now equip our BASE-layer item — should keep both.
        equip(self.character_state, self.item_state)

        self.assertEqual(
            EquippedItem.objects.filter(character=self.character).count(),
            2,
        )

    def test_equip_multi_region_creates_all_rows(self) -> None:
        plate_template = ItemTemplateFactory(name="Equip Test Plate")
        for region in (BodyRegion.TORSO, BodyRegion.LEFT_ARM, BodyRegion.RIGHT_ARM):
            TemplateSlotFactory(
                template=plate_template,
                body_region=region,
                equipment_layer=EquipmentLayer.OUTER,
            )
        plate_obj = ObjectDBFactory(
            db_key="EquipTestPlateObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        plate_obj.location = self.character
        plate_obj.save()
        plate = ItemInstanceFactory(template=plate_template, game_object=plate_obj)
        plate_state = ItemState(plate, context=MagicMock())

        equip(self.character_state, plate_state)

        self.assertEqual(
            EquippedItem.objects.filter(character=self.character, item_instance=plate).count(),
            3,
        )

    def test_equip_denied_raises(self) -> None:
        with patch.object(ItemState, "can_equip", return_value=False):
            with self.assertRaises(PermissionDenied):
                equip(self.character_state, self.item_state)

    def test_equip_same_item_already_equipped_is_idempotent(self) -> None:
        """Re-equipping an already-equipped item is a silent no-op (UI double-click safe)."""
        equip(self.character_state, self.item_state)
        # Second equip should not raise and should leave exactly one row.
        equip(self.character_state, self.item_state)
        self.assertEqual(
            EquippedItem.objects.filter(character=self.character, item_instance=self.item).count(),
            1,
        )


class UnequipTests(TestCase):
    """Cover the three behaviors of ``unequip``."""

    def setUp(self) -> None:
        # Same per-test setUp pattern — DbHolder isn't deepcopy-safe, so
        # setUpTestData breaks for Evennia typeclasses.
        self.account = AccountFactory()
        self.room = ObjectDBFactory(
            db_key="UnequipTestRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.character = CharacterFactory(
            db_key="UnequipTestChar",
            location=self.room,
        )
        self.character.db_account = self.account
        self.character.save()
        self.sheet = CharacterSheetFactory(character=self.character)

        # Single TORSO/BASE slot template.
        self.template = ItemTemplateFactory(name="Unequip Test Shirt")
        TemplateSlotFactory(
            template=self.template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        item_obj = ObjectDBFactory(
            db_key="UnequipTestItemObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        item_obj.location = self.character
        item_obj.save()
        self.item = ItemInstanceFactory(template=self.template, game_object=item_obj)

        ctx = MagicMock()
        self.character_state = CharacterState(self.character, context=ctx)
        self.item_state = ItemState(self.item, context=ctx)

    def test_unequip_removes_row_and_keeps_item_in_inventory(self) -> None:
        equip_item(
            character_sheet=self.sheet,
            item_instance=self.item,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        unequip(self.character_state, self.item_state)
        self.assertFalse(
            EquippedItem.objects.filter(item_instance=self.item).exists(),
        )
        self.item.game_object.refresh_from_db()
        self.assertEqual(self.item.game_object.location, self.character)

    def test_unequip_multi_region_removes_all_rows(self) -> None:
        plate_template = ItemTemplateFactory(name="Unequip Test Plate")
        for region in (BodyRegion.TORSO, BodyRegion.LEFT_ARM, BodyRegion.RIGHT_ARM):
            TemplateSlotFactory(
                template=plate_template,
                body_region=region,
                equipment_layer=EquipmentLayer.OUTER,
            )
        plate_obj = ObjectDBFactory(
            db_key="UnequipTestPlateObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        plate_obj.location = self.character
        plate_obj.save()
        plate = ItemInstanceFactory(template=plate_template, game_object=plate_obj)
        plate_state = ItemState(plate, context=MagicMock())

        for region in (BodyRegion.TORSO, BodyRegion.LEFT_ARM, BodyRegion.RIGHT_ARM):
            equip_item(
                character_sheet=self.sheet,
                item_instance=plate,
                body_region=region,
                equipment_layer=EquipmentLayer.OUTER,
            )

        unequip(self.character_state, plate_state)

        self.assertFalse(EquippedItem.objects.filter(item_instance=plate).exists())

    def test_unequip_not_equipped_raises(self) -> None:
        with self.assertRaises(NotEquipped):
            unequip(self.character_state, self.item_state)
