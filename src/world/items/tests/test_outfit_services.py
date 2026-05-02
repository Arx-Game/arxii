"""Tests for outfit-related service functions."""

from __future__ import annotations

from unittest.mock import MagicMock

from django.db import IntegrityError
from django.test import TestCase

from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    ObjectDBFactory,
)
from flows.object_states.character_state import CharacterState
from flows.object_states.outfit_state import OutfitState
from flows.service_functions.outfits import (
    add_outfit_slot,
    apply_outfit,
    delete_outfit,
    remove_outfit_slot,
    save_outfit,
    undress,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.exceptions import (
    NotAContainer,
    NotReachable,
    OutfitIncomplete,
    PermissionDenied,
    SlotIncompatible,
)
from world.items.factories import (
    ItemInstanceFactory,
    ItemTemplateFactory,
    OutfitFactory,
    OutfitSlotFactory,
    TemplateSlotFactory,
)
from world.items.models import EquippedItem, ItemInstance, Outfit, OutfitSlot
from world.items.services import equip_item


class ApplyOutfitTests(TestCase):
    """Cover the validation + happy paths of ``apply_outfit``."""

    def setUp(self) -> None:
        # Per-test setUp — DbHolder isn't deepcopy-safe, so setUpTestData
        # breaks for Evennia typeclasses (matches test_inventory_services
        # pattern).
        self.account = AccountFactory()
        self.room = ObjectDBFactory(
            db_key="ApplyOutfitRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.character = CharacterFactory(
            db_key="ApplyOutfitChar",
            location=self.room,
        )
        self.character.db_account = self.account
        self.character.save()
        self.sheet = CharacterSheetFactory(character=self.character)

        # Wardrobe in the same room as the actor.
        wardrobe_template = ItemTemplateFactory(
            name="ApplyOutfitWardrobe",
            is_wardrobe=True,
            is_container=True,
        )
        wardrobe_obj = ObjectDBFactory(
            db_key="ApplyOutfitWardrobeObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        wardrobe_obj.location = self.room
        wardrobe_obj.save()
        self.wardrobe = ItemInstanceFactory(
            template=wardrobe_template,
            game_object=wardrobe_obj,
        )

        # Templates: a TORSO/BASE shirt and a LEFT_HAND/BASE glove (distinct
        # body regions so they don't conflict with each other).
        self.shirt_template = ItemTemplateFactory(name="ApplyOutfitShirt")
        TemplateSlotFactory(
            template=self.shirt_template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        self.glove_template = ItemTemplateFactory(name="ApplyOutfitGlove")
        TemplateSlotFactory(
            template=self.glove_template,
            body_region=BodyRegion.LEFT_HAND,
            equipment_layer=EquipmentLayer.BASE,
        )

        # Two distinct items in the actor's possession.
        shirt_obj = ObjectDBFactory(
            db_key="ApplyOutfitShirtObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        shirt_obj.location = self.character
        shirt_obj.save()
        self.shirt = ItemInstanceFactory(
            template=self.shirt_template,
            game_object=shirt_obj,
        )
        glove_obj = ObjectDBFactory(
            db_key="ApplyOutfitGloveObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        glove_obj.location = self.character
        glove_obj.save()
        self.glove = ItemInstanceFactory(
            template=self.glove_template,
            game_object=glove_obj,
        )

        # Build outfit with a slot referencing each item.
        self.outfit = OutfitFactory(
            character_sheet=self.sheet,
            wardrobe=self.wardrobe,
            name="ApplyOutfitLook",
        )
        OutfitSlotFactory(
            outfit=self.outfit,
            item_instance=self.shirt,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        OutfitSlotFactory(
            outfit=self.outfit,
            item_instance=self.glove,
            body_region=BodyRegion.LEFT_HAND,
            equipment_layer=EquipmentLayer.BASE,
        )

        ctx = MagicMock()
        self.character_state = CharacterState(self.character, context=ctx)
        self.outfit_state = OutfitState(self.outfit, context=ctx)

    def test_apply_equips_all_slots(self) -> None:
        """All outfit slots become EquippedItem rows."""
        apply_outfit(self.character_state, self.outfit_state)

        equipped = EquippedItem.objects.filter(character=self.character)
        self.assertEqual(equipped.count(), 2)
        self.assertTrue(equipped.filter(item_instance=self.shirt).exists())
        self.assertTrue(equipped.filter(item_instance=self.glove).exists())

    def test_apply_swaps_conflicting_slot(self) -> None:
        """A pre-existing item at TORSO/BASE is auto-swapped for the outfit's shirt."""
        # Pre-equip a different shirt at TORSO/BASE.
        other_shirt_obj = ObjectDBFactory(
            db_key="ApplyOutfitOtherShirtObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        other_shirt_obj.location = self.character
        other_shirt_obj.save()
        other_shirt = ItemInstanceFactory(
            template=self.shirt_template,
            game_object=other_shirt_obj,
        )
        equip_item(
            character_sheet=self.sheet,
            item_instance=other_shirt,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )

        apply_outfit(self.character_state, self.outfit_state)

        # Only the outfit's shirt is at TORSO/BASE — the old one was swapped out.
        torso_rows = EquippedItem.objects.filter(
            character=self.character,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        self.assertEqual(torso_rows.count(), 1)
        self.assertEqual(torso_rows.first().item_instance, self.shirt)

    def test_apply_leaves_unrelated_slots_alone(self) -> None:
        """A pre-existing item at NECK/ACCESSORY survives the apply (no clean-strip)."""
        necklace_template = ItemTemplateFactory(name="ApplyOutfitNecklace")
        TemplateSlotFactory(
            template=necklace_template,
            body_region=BodyRegion.NECK,
            equipment_layer=EquipmentLayer.ACCESSORY,
        )
        necklace_obj = ObjectDBFactory(
            db_key="ApplyOutfitNecklaceObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        necklace_obj.location = self.character
        necklace_obj.save()
        necklace = ItemInstanceFactory(
            template=necklace_template,
            game_object=necklace_obj,
        )
        equip_item(
            character_sheet=self.sheet,
            item_instance=necklace,
            body_region=BodyRegion.NECK,
            equipment_layer=EquipmentLayer.ACCESSORY,
        )

        apply_outfit(self.character_state, self.outfit_state)

        self.assertTrue(
            EquippedItem.objects.filter(
                character=self.character,
                item_instance=necklace,
            ).exists()
        )

    def test_apply_rejects_when_wardrobe_not_in_reach(self) -> None:
        """Wardrobe in another room → NotReachable, no slots equipped."""
        other_room = ObjectDBFactory(
            db_key="ApplyOutfitOtherRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.wardrobe.game_object.location = other_room
        self.wardrobe.game_object.save()

        with self.assertRaises(NotReachable):
            apply_outfit(self.character_state, self.outfit_state)
        self.assertFalse(EquippedItem.objects.filter(character=self.character).exists())

    def test_apply_rejects_when_item_not_in_reach(self) -> None:
        """An outfit slot's item lives in another character's inventory → OutfitIncomplete.

        Updated for I2: per-slot unreachability now raises the clearer
        OutfitIncomplete rather than a bare NotReachable, so the UI can
        say "Some pieces of that outfit are missing." rather than the
        ambiguous "You can't reach that."
        """
        bystander = CharacterFactory(
            db_key="ApplyOutfitBystander",
            location=self.room,
        )
        self.shirt.game_object.location = bystander
        self.shirt.game_object.save()

        with self.assertRaises(OutfitIncomplete):
            apply_outfit(self.character_state, self.outfit_state)
        # Whole transaction rolls back — no rows created.
        self.assertFalse(EquippedItem.objects.filter(character=self.character).exists())

    def test_apply_collects_all_missing_slots_before_raising(self) -> None:
        """When multiple items are unreachable, OutfitIncomplete is raised once.

        Regression for I2: prior code raised NotReachable on the first
        unreachable item, so the user never learned about subsequent
        missing pieces. Now the service collects all unreachable slots
        in a single pass before raising.
        """
        bystander = CharacterFactory(
            db_key="ApplyOutfitBystanderTwo",
            location=self.room,
        )
        # Both shirt and glove are unreachable.
        self.shirt.game_object.location = bystander
        self.shirt.game_object.save()
        self.glove.game_object.location = bystander
        self.glove.game_object.save()

        with self.assertRaises(OutfitIncomplete):
            apply_outfit(self.character_state, self.outfit_state)
        self.assertFalse(EquippedItem.objects.filter(character=self.character).exists())

    def test_apply_rejects_outfit_belonging_to_different_character(self) -> None:
        """An outfit owned by another sheet → PermissionDenied."""
        other_character = CharacterFactory(
            db_key="ApplyOutfitOtherChar",
            location=self.room,
        )
        other_sheet = CharacterSheetFactory(character=other_character)
        other_outfit = OutfitFactory(
            character_sheet=other_sheet,
            wardrobe=self.wardrobe,
            name="ApplyOutfitOtherLook",
        )
        OutfitSlotFactory(
            outfit=other_outfit,
            item_instance=self.shirt,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        other_outfit_state = OutfitState(other_outfit, context=MagicMock())

        with self.assertRaises(PermissionDenied):
            apply_outfit(self.character_state, other_outfit_state)


class UndressTests(TestCase):
    """Cover ``undress`` for naked, single-item, and multi-item characters."""

    def setUp(self) -> None:
        self.account = AccountFactory()
        self.room = ObjectDBFactory(
            db_key="UndressTestRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.character = CharacterFactory(
            db_key="UndressTestChar",
            location=self.room,
        )
        self.character.db_account = self.account
        self.character.save()
        self.sheet = CharacterSheetFactory(character=self.character)

        # Three distinct items at three distinct body regions so they coexist.
        self.items: list = []
        for idx, (region, layer, name) in enumerate(
            [
                (BodyRegion.TORSO, EquipmentLayer.BASE, "UndressShirt"),
                (BodyRegion.LEFT_HAND, EquipmentLayer.BASE, "UndressGlove"),
                (BodyRegion.NECK, EquipmentLayer.ACCESSORY, "UndressNecklace"),
            ]
        ):
            template = ItemTemplateFactory(name=f"{name}Template{idx}")
            TemplateSlotFactory(
                template=template,
                body_region=region,
                equipment_layer=layer,
            )
            item_obj = ObjectDBFactory(
                db_key=f"{name}Obj",
                db_typeclass_path="typeclasses.objects.Object",
            )
            item_obj.location = self.character
            item_obj.save()
            item = ItemInstanceFactory(template=template, game_object=item_obj)
            self.items.append(item)

        ctx = MagicMock()
        self.character_state = CharacterState(self.character, context=ctx)

    def _equip_all(self) -> None:
        for item in self.items:
            slot = item.template.cached_slots[0]
            equip_item(
                character_sheet=self.sheet,
                item_instance=item,
                body_region=slot.body_region,
                equipment_layer=slot.equipment_layer,
            )

    def test_undress_removes_all_equipped_items(self) -> None:
        """Three equipped items → zero EquippedItem rows after undress."""
        self._equip_all()
        self.assertEqual(
            EquippedItem.objects.filter(character=self.character).count(),
            3,
        )

        undress(self.character_state)

        self.assertEqual(
            EquippedItem.objects.filter(character=self.character).count(),
            0,
        )

    def test_undress_idempotent_when_naked(self) -> None:
        """Naked character → undress is a no-op, no error raised."""
        self.assertEqual(
            EquippedItem.objects.filter(character=self.character).count(),
            0,
        )

        # Should not raise.
        undress(self.character_state)

        self.assertEqual(
            EquippedItem.objects.filter(character=self.character).count(),
            0,
        )

    def test_undress_keeps_items_in_inventory(self) -> None:
        """After undress, every item's underlying ObjectDB still on character."""
        self._equip_all()

        undress(self.character_state)

        for item in self.items:
            item.game_object.refresh_from_db()
            self.assertEqual(item.game_object.location, self.character)


class _OutfitServiceSetupMixin:
    """Shared setUp building a character + wardrobe + two equipable templates.

    Mirrors the structure of ApplyOutfitTests but tailored for save/delete/slot
    edit testing — provides a wardrobe instance and two distinct templates
    (TORSO/BASE shirt, LEFT_HAND/BASE glove) along with item instances.
    """

    def setUp(self) -> None:
        self.account = AccountFactory()
        self.room = ObjectDBFactory(
            db_key="OutfitSvcRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.character = CharacterFactory(
            db_key="OutfitSvcChar",
            location=self.room,
        )
        self.character.db_account = self.account
        self.character.save()
        self.sheet = CharacterSheetFactory(character=self.character)

        # Wardrobe instance (template flagged is_wardrobe).
        self.wardrobe_template = ItemTemplateFactory(
            name="OutfitSvcWardrobe",
            is_wardrobe=True,
            is_container=True,
        )
        wardrobe_obj = ObjectDBFactory(
            db_key="OutfitSvcWardrobeObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        wardrobe_obj.location = self.room
        wardrobe_obj.save()
        self.wardrobe = ItemInstanceFactory(
            template=self.wardrobe_template,
            game_object=wardrobe_obj,
        )

        # Shirt template + instance (TORSO/BASE) — owned by the actor's account.
        self.shirt_template = ItemTemplateFactory(name="OutfitSvcShirt")
        TemplateSlotFactory(
            template=self.shirt_template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        shirt_obj = ObjectDBFactory(
            db_key="OutfitSvcShirtObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        shirt_obj.location = self.character
        shirt_obj.save()
        self.shirt = ItemInstanceFactory(
            template=self.shirt_template,
            game_object=shirt_obj,
            owner=self.account,
        )

        # Glove template + instance (LEFT_HAND/BASE) — owned by the actor's account.
        self.glove_template = ItemTemplateFactory(name="OutfitSvcGlove")
        TemplateSlotFactory(
            template=self.glove_template,
            body_region=BodyRegion.LEFT_HAND,
            equipment_layer=EquipmentLayer.BASE,
        )
        glove_obj = ObjectDBFactory(
            db_key="OutfitSvcGloveObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        glove_obj.location = self.character
        glove_obj.save()
        self.glove = ItemInstanceFactory(
            template=self.glove_template,
            game_object=glove_obj,
            owner=self.account,
        )


class SaveOutfitTests(_OutfitServiceSetupMixin, TestCase):
    """Cover snapshot-from-current-loadout behavior of ``save_outfit``."""

    def test_save_creates_outfit_with_current_loadout(self) -> None:
        """Two equipped items become two OutfitSlot rows on the new Outfit."""
        equip_item(
            character_sheet=self.sheet,
            item_instance=self.shirt,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        equip_item(
            character_sheet=self.sheet,
            item_instance=self.glove,
            body_region=BodyRegion.LEFT_HAND,
            equipment_layer=EquipmentLayer.BASE,
        )

        outfit = save_outfit(
            character_sheet=self.sheet,
            wardrobe=self.wardrobe,
            name="SnapshotLook",
        )

        self.assertEqual(outfit.character_sheet, self.sheet)
        self.assertEqual(outfit.wardrobe, self.wardrobe)
        self.assertEqual(outfit.name, "SnapshotLook")
        slots = outfit.slots.all()
        self.assertEqual(slots.count(), 2)
        slot_tuples = {(s.item_instance_id, s.body_region, s.equipment_layer) for s in slots}
        self.assertEqual(
            slot_tuples,
            {
                (self.shirt.id, BodyRegion.TORSO, EquipmentLayer.BASE),
                (self.glove.id, BodyRegion.LEFT_HAND, EquipmentLayer.BASE),
            },
        )

    def test_save_with_naked_character_creates_empty_outfit(self) -> None:
        """No equipped items → outfit with zero slots (still created)."""
        outfit = save_outfit(
            character_sheet=self.sheet,
            wardrobe=self.wardrobe,
            name="NakedLook",
        )

        self.assertIsInstance(outfit, Outfit)
        self.assertEqual(outfit.slots.count(), 0)

    def test_save_rejects_when_template_not_wardrobe(self) -> None:
        """Wardrobe arg pointing to a non-wardrobe item → NotAContainer."""
        non_wardrobe_obj = ObjectDBFactory(
            db_key="OutfitSvcNonWardrobeObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        non_wardrobe_obj.location = self.room
        non_wardrobe_obj.save()
        non_wardrobe = ItemInstanceFactory(
            template=self.shirt_template,  # not is_wardrobe
            game_object=non_wardrobe_obj,
        )

        with self.assertRaises(NotAContainer):
            save_outfit(
                character_sheet=self.sheet,
                wardrobe=non_wardrobe,
                name="ShouldFail",
            )
        self.assertFalse(
            Outfit.objects.filter(character_sheet=self.sheet, name="ShouldFail").exists()
        )

    def test_save_rejects_duplicate_name(self) -> None:
        """Same (character_sheet, name) violates the DB unique constraint."""
        save_outfit(
            character_sheet=self.sheet,
            wardrobe=self.wardrobe,
            name="DupeLook",
        )

        with self.assertRaises(IntegrityError):
            save_outfit(
                character_sheet=self.sheet,
                wardrobe=self.wardrobe,
                name="DupeLook",
            )

    def test_save_rejects_when_wardrobe_in_other_room(self) -> None:
        """Wardrobe out of reach (different room) → NotReachable, no Outfit row created.

        Regression test for I4: previously the docstring claimed REST handled
        reach validation, but no permission class actually checked it. A
        player could POST any wardrobe pk on the planet.
        """
        other_room = ObjectDBFactory(
            db_key="OutfitSvcOtherRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.wardrobe.game_object.location = other_room
        self.wardrobe.game_object.save()

        with self.assertRaises(NotReachable):
            save_outfit(
                character_sheet=self.sheet,
                wardrobe=self.wardrobe,
                name="UnreachableWardrobeLook",
            )
        self.assertFalse(
            Outfit.objects.filter(
                character_sheet=self.sheet,
                name="UnreachableWardrobeLook",
            ).exists()
        )


class DeleteOutfitTests(_OutfitServiceSetupMixin, TestCase):
    """Cover ``delete_outfit`` — outfit + slots gone, items untouched."""

    def _build_outfit_with_slots(self) -> Outfit:
        outfit = OutfitFactory(
            character_sheet=self.sheet,
            wardrobe=self.wardrobe,
            name="DeleteLook",
        )
        OutfitSlotFactory(
            outfit=outfit,
            item_instance=self.shirt,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        OutfitSlotFactory(
            outfit=outfit,
            item_instance=self.glove,
            body_region=BodyRegion.LEFT_HAND,
            equipment_layer=EquipmentLayer.BASE,
        )
        return outfit

    def test_delete_removes_outfit_and_slots(self) -> None:
        """Outfit row + its slot rows both vanish."""
        outfit = self._build_outfit_with_slots()
        outfit_id = outfit.id

        delete_outfit(outfit)

        self.assertFalse(Outfit.objects.filter(id=outfit_id).exists())
        self.assertFalse(OutfitSlot.objects.filter(outfit_id=outfit_id).exists())

    def test_delete_does_not_touch_items(self) -> None:
        """Item instances persist after the outfit is deleted."""
        outfit = self._build_outfit_with_slots()
        shirt_id = self.shirt.id
        glove_id = self.glove.id

        delete_outfit(outfit)

        self.assertTrue(ItemInstance.objects.filter(id=shirt_id).exists())
        self.assertTrue(ItemInstance.objects.filter(id=glove_id).exists())


class OutfitSlotEditTests(_OutfitServiceSetupMixin, TestCase):
    """Cover ``add_outfit_slot`` / ``remove_outfit_slot``."""

    def setUp(self) -> None:
        super().setUp()
        self.outfit = OutfitFactory(
            character_sheet=self.sheet,
            wardrobe=self.wardrobe,
            name="SlotEditLook",
        )

    def test_add_slot_creates_row(self) -> None:
        """Empty outfit + add → 1 OutfitSlot row at the requested slot."""
        slot = add_outfit_slot(
            outfit=self.outfit,
            item_instance=self.shirt,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )

        self.assertEqual(self.outfit.slots.count(), 1)
        self.assertEqual(slot.item_instance, self.shirt)
        self.assertEqual(slot.body_region, BodyRegion.TORSO)
        self.assertEqual(slot.equipment_layer, EquipmentLayer.BASE)

    def test_add_slot_replaces_existing_at_same_region_layer(self) -> None:
        """Two adds at the same (region, layer) → only the new slot remains."""
        # First shirt at TORSO/BASE.
        OutfitSlotFactory(
            outfit=self.outfit,
            item_instance=self.shirt,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        # Build a second TORSO/BASE-compatible item, owned by the same account.
        other_shirt_obj = ObjectDBFactory(
            db_key="OutfitSvcOtherShirtObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        other_shirt_obj.location = self.character
        other_shirt_obj.save()
        other_shirt = ItemInstanceFactory(
            template=self.shirt_template,
            game_object=other_shirt_obj,
            owner=self.account,
        )

        add_outfit_slot(
            outfit=self.outfit,
            item_instance=other_shirt,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )

        slots = self.outfit.slots.all()
        self.assertEqual(slots.count(), 1)
        self.assertEqual(slots.first().item_instance, other_shirt)

    def test_add_slot_rejects_template_incompatible(self) -> None:
        """Item whose template doesn't declare (region, layer) → SlotIncompatible."""
        with self.assertRaises(SlotIncompatible):
            add_outfit_slot(
                outfit=self.outfit,
                item_instance=self.shirt,  # only declares TORSO/BASE
                body_region=BodyRegion.LEFT_HAND,
                equipment_layer=EquipmentLayer.BASE,
            )
        self.assertEqual(self.outfit.slots.count(), 0)

    def test_add_slot_rejects_item_not_owned_by_character(self) -> None:
        """Item owned by another account → PermissionDenied, no slot row created.

        Outfits are configuration. The configuration layer's ownership boundary
        is account-level (an account building an outfit can only reference
        items its account owns). Apply-time enforces possession/reach
        separately.
        """
        other_account = AccountFactory(username="OutfitSvcSlotOtherAccount")
        foreign_shirt_obj = ObjectDBFactory(
            db_key="OutfitSvcSlotForeignShirtObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        foreign_shirt = ItemInstanceFactory(
            template=self.shirt_template,
            game_object=foreign_shirt_obj,
            owner=other_account,
        )

        with self.assertRaises(PermissionDenied):
            add_outfit_slot(
                outfit=self.outfit,
                item_instance=foreign_shirt,
                body_region=BodyRegion.TORSO,
                equipment_layer=EquipmentLayer.BASE,
            )
        self.assertEqual(self.outfit.slots.count(), 0)

    def test_remove_slot_deletes_row(self) -> None:
        """Existing slot → remove → 0 rows."""
        OutfitSlotFactory(
            outfit=self.outfit,
            item_instance=self.shirt,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        self.assertEqual(self.outfit.slots.count(), 1)

        remove_outfit_slot(
            outfit=self.outfit,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )

        self.assertEqual(self.outfit.slots.count(), 0)

    def test_remove_slot_idempotent_when_no_match(self) -> None:
        """No slot at (region, layer) → remove is a no-op, no exception."""
        # Outfit has no slots — should not raise.
        remove_outfit_slot(
            outfit=self.outfit,
            body_region=BodyRegion.NECK,
            equipment_layer=EquipmentLayer.ACCESSORY,
        )

        self.assertEqual(self.outfit.slots.count(), 0)
