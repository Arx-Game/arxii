"""Tests for item-specific actions (equip, unequip, put_in, take_out)."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from actions.definitions.items import (
    EquipAction,
    PutInAction,
    TakeOutAction,
    UnequipAction,
)
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
    TemplateSlotFactory,
)
from world.items.models import EquippedItem
from world.items.services import equip_item


class EquipActionTests(TestCase):
    def _build_actor_and_item(self) -> tuple:
        room = ObjectDBFactory(
            db_key="EquipActionRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        account = AccountFactory(username="equip_action_account")
        actor = CharacterFactory(db_key="EquipActionAlice", location=room)
        actor.db_account = account
        actor.save()
        CharacterSheetFactory(character=actor)

        template = ItemTemplateFactory(name="Equip Action Shirt")
        TemplateSlotFactory(
            template=template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        item_obj = ObjectDBFactory(db_key="EquipActionShirt", location=actor)
        item_instance = ItemInstanceFactory(template=template, game_object=item_obj)
        return room, actor, item_obj, item_instance

    def test_equip_creates_equipped_row(self) -> None:
        room, actor, item_obj, item_instance = self._build_actor_and_item()

        action = EquipAction()
        with patch.object(room, "msg_contents"):
            result = action.run(actor, target=item_obj)

        assert result.success is True
        assert EquippedItem.objects.filter(
            character=actor,
            item_instance=item_instance,
        ).exists()

    def test_equip_without_item_instance_fails_gracefully(self) -> None:
        room = ObjectDBFactory(
            db_key="EquipActionNoInstanceRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        actor = CharacterFactory(db_key="EquipActionNoInstanceActor", location=room)
        bare_object = ObjectDBFactory(db_key="EquipActionBareObject", location=actor)

        action = EquipAction()
        result = action.run(actor, target=bare_object)
        assert result.success is False
        assert result.message == "That can't be equipped."

    def test_equip_inventory_error_surfaces_user_message(self) -> None:
        """A denied equip surfaces the typed exception's user_message."""
        _room, actor, item_obj, _ = self._build_actor_and_item()

        from world.items.exceptions import PermissionDenied

        action = EquipAction()
        with patch(
            "actions.definitions.items.equip",
            side_effect=PermissionDenied,
        ):
            result = action.run(actor, target=item_obj)

        assert result.success is False
        assert result.message == PermissionDenied.user_message


class UnequipActionTests(TestCase):
    def test_unequip_removes_equipped_row(self) -> None:
        room = ObjectDBFactory(
            db_key="UnequipActionRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        actor = CharacterFactory(db_key="UnequipActionAlice", location=room)
        sheet = CharacterSheetFactory(character=actor)

        template = ItemTemplateFactory(name="Unequip Action Shirt")
        TemplateSlotFactory(
            template=template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        item_obj = ObjectDBFactory(db_key="UnequipActionShirt", location=actor)
        item_instance = ItemInstanceFactory(template=template, game_object=item_obj)
        equip_item(
            character_sheet=sheet,
            item_instance=item_instance,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )

        action = UnequipAction()
        with patch.object(room, "msg_contents"):
            result = action.run(actor, target=item_obj)

        assert result.success is True
        assert not EquippedItem.objects.filter(item_instance=item_instance).exists()

    def test_unequip_when_not_equipped_surfaces_user_message(self) -> None:
        room = ObjectDBFactory(
            db_key="UnequipActionNotEquippedRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        actor = CharacterFactory(db_key="UnequipActionNotEquippedActor", location=room)

        template = ItemTemplateFactory(name="Unequip Action NotEquipped Shirt")
        TemplateSlotFactory(
            template=template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        item_obj = ObjectDBFactory(
            db_key="UnequipActionNotEquippedShirt",
            location=actor,
        )
        ItemInstanceFactory(template=template, game_object=item_obj)

        action = UnequipAction()
        result = action.run(actor, target=item_obj)
        assert result.success is False

        from world.items.exceptions import NotEquipped

        assert result.message == NotEquipped.user_message


class PutInActionTests(TestCase):
    def _build_scene(self) -> tuple:
        room = ObjectDBFactory(
            db_key="PutInActionRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        actor = CharacterFactory(db_key="PutInActionAlice", location=room)

        container_template = ItemTemplateFactory(
            name="PutInAction Bag",
            is_container=True,
            container_capacity=2,
            container_max_item_size=5,
            supports_open_close=True,
        )
        container_obj = ObjectDBFactory(db_key="PutInActionBag", location=actor)
        container = ItemInstanceFactory(
            template=container_template,
            game_object=container_obj,
            is_open=True,
        )

        item_template = ItemTemplateFactory(name="PutInAction Coin", size=1)
        item_obj = ObjectDBFactory(db_key="PutInActionCoin", location=actor)
        item_instance = ItemInstanceFactory(template=item_template, game_object=item_obj)
        return room, actor, item_obj, item_instance, container_obj, container

    def test_put_in_sets_contained_in(self) -> None:
        room, actor, item_obj, item_instance, container_obj, container = self._build_scene()

        action = PutInAction()
        with patch.object(room, "msg_contents"):
            result = action.run(actor, target=item_obj, container=container_obj)

        assert result.success is True
        item_instance.refresh_from_db()
        assert item_instance.contained_in == container

    def test_put_in_missing_container_arg_fails(self) -> None:
        room = ObjectDBFactory(
            db_key="PutInActionMissingContainerRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        actor = CharacterFactory(db_key="PutInActionMissingContainerActor", location=room)
        item_obj = ObjectDBFactory(db_key="PutInActionMissingContainerItem", location=actor)
        ItemInstanceFactory(game_object=item_obj)

        action = PutInAction()
        result = action.run(actor, target=item_obj)
        assert result.success is False
        assert result.message == "Put what into what?"

    def test_put_in_closed_container_surfaces_user_message(self) -> None:
        _room, actor, item_obj, _, container_obj, container = self._build_scene()
        container.is_open = False
        container.save()

        action = PutInAction()
        result = action.run(actor, target=item_obj, container=container_obj)
        assert result.success is False

        from world.items.exceptions import ContainerClosed

        assert result.message == ContainerClosed.user_message

    def test_put_in_non_item_container_fails_gracefully(self) -> None:
        """Container without an ItemInstance row returns a clean error."""
        room = ObjectDBFactory(
            db_key="PutInActionBareContainerRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        actor = CharacterFactory(db_key="PutInActionBareContainerActor", location=room)
        item_obj = ObjectDBFactory(db_key="PutInActionItemForBare", location=actor)
        ItemInstanceFactory(game_object=item_obj)
        bare_container = ObjectDBFactory(
            db_key="PutInActionBareContainer",
            location=actor,
        )

        action = PutInAction()
        result = action.run(actor, target=item_obj, container=bare_container)
        assert result.success is False
        assert result.message == "That isn't a container."


class TakeOutActionTests(TestCase):
    def _build_scene(self) -> tuple:
        room = ObjectDBFactory(
            db_key="TakeOutActionRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        actor = CharacterFactory(db_key="TakeOutActionAlice", location=room)

        container_template = ItemTemplateFactory(
            name="TakeOutAction Box",
            is_container=True,
        )
        container_obj = ObjectDBFactory(db_key="TakeOutActionBox", location=actor)
        container = ItemInstanceFactory(
            template=container_template,
            game_object=container_obj,
        )

        item_obj = ObjectDBFactory(db_key="TakeOutActionItem", location=container_obj)
        item_instance = ItemInstanceFactory(game_object=item_obj, contained_in=container)
        return room, actor, item_obj, item_instance, container

    def test_take_out_clears_contained_in_and_moves_to_actor(self) -> None:
        room, actor, item_obj, item_instance, _container = self._build_scene()

        action = TakeOutAction()
        with patch.object(room, "msg_contents"):
            result = action.run(actor, target=item_obj)

        assert result.success is True
        item_instance.refresh_from_db()
        item_obj.refresh_from_db()
        assert item_instance.contained_in is None
        assert item_obj.location == actor

    def test_take_out_without_item_instance_fails_gracefully(self) -> None:
        room = ObjectDBFactory(
            db_key="TakeOutActionNoInstanceRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        actor = CharacterFactory(db_key="TakeOutActionNoInstanceActor", location=room)
        bare_object = ObjectDBFactory(db_key="TakeOutActionBareObject", location=actor)

        action = TakeOutAction()
        result = action.run(actor, target=bare_object)
        assert result.success is False
        assert result.message == "That can't be taken out."
