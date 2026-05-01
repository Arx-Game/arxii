"""Tests for outfit-specific actions (apply_outfit, undress)."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from actions.definitions.outfits import ApplyOutfitAction, UndressAction
from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    ObjectDBFactory,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import (
    ItemInstanceFactory,
    ItemTemplateFactory,
    OutfitFactory,
    OutfitSlotFactory,
    TemplateSlotFactory,
)
from world.items.models import EquippedItem
from world.items.services import equip_item


class ApplyOutfitActionTests(TestCase):
    def _build_actor_outfit_and_items(self) -> tuple:
        room = ObjectDBFactory(
            db_key="ApplyOutfitActionRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        account = AccountFactory(username="apply_outfit_action_account")
        actor = CharacterFactory(db_key="ApplyOutfitActionAlice", location=room)
        actor.db_account = account
        actor.save()
        sheet = CharacterSheetFactory(character=actor)

        # Wardrobe lives in the room (in reach of the actor).
        wardrobe_template = ItemTemplateFactory(
            name="ApplyOutfitActionWardrobe",
            is_wardrobe=True,
            is_container=True,
        )
        wardrobe_obj = ObjectDBFactory(
            db_key="ApplyOutfitActionWardrobeObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        wardrobe_obj.location = room
        wardrobe_obj.save()
        wardrobe = ItemInstanceFactory(
            template=wardrobe_template,
            game_object=wardrobe_obj,
        )

        # Two distinct items at distinct body regions.
        shirt_template = ItemTemplateFactory(name="ApplyOutfitActionShirt")
        TemplateSlotFactory(
            template=shirt_template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        glove_template = ItemTemplateFactory(name="ApplyOutfitActionGlove")
        TemplateSlotFactory(
            template=glove_template,
            body_region=BodyRegion.LEFT_HAND,
            equipment_layer=EquipmentLayer.BASE,
        )

        shirt_obj = ObjectDBFactory(
            db_key="ApplyOutfitActionShirtObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        shirt_obj.location = actor
        shirt_obj.save()
        shirt = ItemInstanceFactory(template=shirt_template, game_object=shirt_obj)

        glove_obj = ObjectDBFactory(
            db_key="ApplyOutfitActionGloveObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        glove_obj.location = actor
        glove_obj.save()
        glove = ItemInstanceFactory(template=glove_template, game_object=glove_obj)

        outfit = OutfitFactory(
            character_sheet=sheet,
            wardrobe=wardrobe,
            name="ApplyOutfitActionLook",
        )
        OutfitSlotFactory(
            outfit=outfit,
            item_instance=shirt,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        OutfitSlotFactory(
            outfit=outfit,
            item_instance=glove,
            body_region=BodyRegion.LEFT_HAND,
            equipment_layer=EquipmentLayer.BASE,
        )
        return room, actor, outfit, shirt, glove

    def test_happy_path_equips_outfit_pieces(self) -> None:
        room, actor, outfit, shirt, glove = self._build_actor_outfit_and_items()

        action = ApplyOutfitAction()
        with patch.object(room, "msg_contents"):
            result = action.run(actor, outfit_id=outfit.pk)

        assert result.success is True
        assert EquippedItem.objects.filter(
            character=actor,
            item_instance=shirt,
        ).exists()
        assert EquippedItem.objects.filter(
            character=actor,
            item_instance=glove,
        ).exists()

    def test_unknown_outfit_id_returns_failure(self) -> None:
        room = ObjectDBFactory(
            db_key="ApplyOutfitActionUnknownRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        actor = CharacterFactory(db_key="ApplyOutfitActionUnknownAlice", location=room)
        CharacterSheetFactory(character=actor)

        action = ApplyOutfitAction()
        result = action.run(actor, outfit_id=999_999)

        assert result.success is False
        assert result.message == "That outfit no longer exists."

    def test_missing_outfit_id_returns_failure(self) -> None:
        room = ObjectDBFactory(
            db_key="ApplyOutfitActionMissingRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        actor = CharacterFactory(db_key="ApplyOutfitActionMissingAlice", location=room)
        CharacterSheetFactory(character=actor)

        action = ApplyOutfitAction()
        result = action.run(actor)

        assert result.success is False
        assert result.message == "Wear which outfit?"

    def test_inventory_error_surfaces_user_message(self) -> None:
        _room, actor, outfit, _shirt, _glove = self._build_actor_outfit_and_items()

        from world.items.exceptions import NotReachable

        action = ApplyOutfitAction()
        with patch(
            "actions.definitions.outfits.apply_outfit_service",
            side_effect=NotReachable,
        ):
            result = action.run(actor, outfit_id=outfit.pk)

        assert result.success is False
        assert result.message == NotReachable.user_message


class UndressActionTests(TestCase):
    def _build_actor_with_equipped_items(self, count: int = 2) -> tuple:
        room = ObjectDBFactory(
            db_key="UndressActionRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        actor = CharacterFactory(db_key="UndressActionAlice", location=room)
        sheet = CharacterSheetFactory(character=actor)

        slots = [
            (BodyRegion.TORSO, EquipmentLayer.BASE, "UndressActionShirt"),
            (BodyRegion.LEFT_HAND, EquipmentLayer.BASE, "UndressActionGlove"),
            (BodyRegion.NECK, EquipmentLayer.ACCESSORY, "UndressActionNecklace"),
        ][:count]

        for region, layer, name in slots:
            template = ItemTemplateFactory(name=f"{name}Template")
            TemplateSlotFactory(
                template=template,
                body_region=region,
                equipment_layer=layer,
            )
            item_obj = ObjectDBFactory(
                db_key=f"{name}Obj",
                db_typeclass_path="typeclasses.objects.Object",
            )
            item_obj.location = actor
            item_obj.save()
            item = ItemInstanceFactory(template=template, game_object=item_obj)
            equip_item(
                character_sheet=sheet,
                item_instance=item,
                body_region=region,
                equipment_layer=layer,
            )

        return room, actor

    def test_happy_path_unequips_all_items(self) -> None:
        room, actor = self._build_actor_with_equipped_items(count=2)
        assert EquippedItem.objects.filter(character=actor).count() == 2

        action = UndressAction()
        with patch.object(room, "msg_contents"):
            result = action.run(actor)

        assert result.success is True
        assert EquippedItem.objects.filter(character=actor).count() == 0

    def test_undress_naked_character_returns_success(self) -> None:
        room = ObjectDBFactory(
            db_key="UndressActionNakedRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        actor = CharacterFactory(db_key="UndressActionNakedAlice", location=room)
        CharacterSheetFactory(character=actor)
        assert EquippedItem.objects.filter(character=actor).count() == 0

        action = UndressAction()
        with patch.object(room, "msg_contents"):
            result = action.run(actor)

        assert result.success is True
        assert EquippedItem.objects.filter(character=actor).count() == 0

    def test_inventory_error_surfaces_user_message(self) -> None:
        _room, actor = self._build_actor_with_equipped_items(count=1)

        from world.items.exceptions import NotReachable

        action = UndressAction()
        with patch(
            "actions.definitions.outfits.undress_service",
            side_effect=NotReachable,
        ):
            result = action.run(actor)

        assert result.success is False
        assert result.message == NotReachable.user_message
