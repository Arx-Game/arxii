"""Tests for LookAtItemAction."""

from __future__ import annotations

from django.test import TestCase

from actions.definitions.perception import LookAtItemAction
from evennia_extensions.factories import (
    AccountFactory,
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


class LookAtItemActionTests(TestCase):
    def setUp(self) -> None:
        self.actor = CharacterSheetFactory(character__db_key="LookActor").character
        self.actor_account = AccountFactory(username="actor_account")
        self.actor_account.is_staff = False
        self.actor_account.save()
        self.actor.db_account = self.actor_account
        self.actor.save()

        self.target = CharacterSheetFactory(character__db_key="LookTarget").character
        self.target.db.desc = "A poised stranger."
        self.target.save()

    def _equip(
        self,
        character,
        name: str,
        region: str,
        layer: str,
    ):
        template = ItemTemplateFactory(name=name)
        TemplateSlotFactory(
            template=template,
            body_region=region,
            equipment_layer=layer,
        )
        item_obj = ObjectDBFactory(
            db_key=f"{name}_obj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        item = ItemInstanceFactory(template=template, game_object=item_obj)
        EquippedItem.objects.create(
            character=character.sheet_data,
            item_instance=item,
            body_region=region,
            equipment_layer=layer,
        )
        return item

    def test_visible_item_on_owner_returns_appearance(self) -> None:
        self._equip(self.target, "Hat", BodyRegion.HEAD, EquipmentLayer.OUTER)
        action = LookAtItemAction()
        result = action.run(self.actor, owner_id=self.target.pk, item_name="hat")
        self.assertTrue(result.success)
        self.assertIn("Hat", result.message or "")

    def test_concealed_item_for_other_observer_fails(self) -> None:
        # Plain coat conceals shirt by default (#2985); non-staff observer can't see it.
        self._equip(
            self.target,
            "Coat",
            BodyRegion.TORSO,
            EquipmentLayer.OVER,
        )
        self._equip(self.target, "Shirt", BodyRegion.TORSO, EquipmentLayer.BASE)
        action = LookAtItemAction()
        result = action.run(self.actor, owner_id=self.target.pk, item_name="shirt")
        self.assertFalse(result.success)
        self.assertIn("don't see", (result.message or "").lower())

    def test_self_can_see_concealed(self) -> None:
        # Concealed shirt visible when looking at self.
        self._equip(
            self.actor,
            "Coat",
            BodyRegion.TORSO,
            EquipmentLayer.OVER,
        )
        self._equip(self.actor, "Shirt", BodyRegion.TORSO, EquipmentLayer.BASE)
        action = LookAtItemAction()
        result = action.run(self.actor, owner_id=self.actor.pk, item_name="shirt")
        self.assertTrue(result.success)

    def test_staff_can_see_concealed(self) -> None:
        # Staff actor can see concealed items.
        self.actor_account.is_staff = True
        self.actor_account.save()
        self._equip(
            self.target,
            "Coat",
            BodyRegion.TORSO,
            EquipmentLayer.OVER,
        )
        self._equip(self.target, "Shirt", BodyRegion.TORSO, EquipmentLayer.BASE)
        action = LookAtItemAction()
        result = action.run(self.actor, owner_id=self.target.pk, item_name="shirt")
        self.assertTrue(result.success)

    def test_unknown_item_name_fails(self) -> None:
        action = LookAtItemAction()
        result = action.run(
            self.actor,
            owner_id=self.target.pk,
            item_name="nonexistent",
        )
        self.assertFalse(result.success)

    def test_no_owner_or_container_fails(self) -> None:
        action = LookAtItemAction()
        result = action.run(self.actor, item_name="hat")
        self.assertFalse(result.success)

    def test_drilled_worn_look_shows_crafted_provenance(self) -> None:
        """New coverage (#3084): the item-scoped provenance subset (moved from
        the dead typeclass path onto ``LookAtItemAction._render_item``) shows
        up on a drilled worn look (``look hat on bob``)."""
        from world.items.factories import QualityTierFactory

        quality = QualityTierFactory(name="Fine", numeric_min=40, numeric_max=59, sort_order=4)
        item = self._equip(self.target, "Hat", BodyRegion.HEAD, EquipmentLayer.OUTER)
        item.quality_tier = quality
        item.save(update_fields=["quality_tier"])

        action = LookAtItemAction()
        result = action.run(self.actor, owner_id=self.target.pk, item_name="hat")

        self.assertTrue(result.success)
        self.assertIn("Of fine quality", result.message or "")


class LookAtItemActionContainerTests(TestCase):
    def setUp(self) -> None:
        self.actor = CharacterSheetFactory(character__db_key="ContActor").character
        self.actor_account = AccountFactory(username="cont_actor_account")
        self.actor_account.is_staff = False
        self.actor_account.save()
        self.actor.db_account = self.actor_account
        self.actor.save()

    def _make_container(self, *, is_open: bool = True):
        template = ItemTemplateFactory(
            name="Pouch",
            is_container=True,
            container_capacity=10,
            supports_open_close=True,
        )
        container_obj = ObjectDBFactory(
            db_key="pouch_obj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        return ItemInstanceFactory(
            template=template,
            game_object=container_obj,
            is_open=is_open,
        )

    def _put_in_container(self, container, name: str):
        item_template = ItemTemplateFactory(name=name)
        item_obj = ObjectDBFactory(
            db_key=f"{name}_obj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        return ItemInstanceFactory(
            template=item_template,
            game_object=item_obj,
            contained_in=container,
        )

    def test_open_container_returns_item_appearance(self) -> None:
        container = self._make_container(is_open=True)
        self._put_in_container(container, "GoldCoin")
        action = LookAtItemAction()
        result = action.run(
            self.actor,
            container_id=container.game_object.pk,
            item_name="goldcoin",
        )
        self.assertTrue(result.success)
        self.assertIn("GoldCoin", result.message or "")

    def test_closed_container_fails(self) -> None:
        container = self._make_container(is_open=False)
        self._put_in_container(container, "GoldCoin")
        action = LookAtItemAction()
        result = action.run(
            self.actor,
            container_id=container.game_object.pk,
            item_name="goldcoin",
        )
        self.assertFalse(result.success)
        self.assertIn("closed", (result.message or "").lower())

    def test_look_at_contained_in_other_room_fails(self) -> None:
        # Container located in a different room than the actor must not be
        # readable. Without the reach check, any open container's contents
        # could be read by POSTing its pk through the action dispatcher.
        actor_room = ObjectDBFactory(
            db_key="ContActorRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        other_room = ObjectDBFactory(
            db_key="ContOtherRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.actor.location = actor_room
        self.actor.save()
        container = self._make_container(is_open=True)
        container.game_object.location = other_room
        container.game_object.save()
        self._put_in_container(container, "GoldCoin")
        action = LookAtItemAction()
        result = action.run(
            self.actor,
            container_id=container.game_object.pk,
            item_name="goldcoin",
        )
        self.assertFalse(result.success)
        self.assertIn("isn't here", (result.message or "").lower())

    def test_look_at_contained_staff_can_see_anywhere(self) -> None:
        # Staff actors bypass the reach check, mirroring the rest of the
        # look pipeline (concealed worn items, etc.).
        self.actor_account.is_staff = True
        self.actor_account.save()
        actor_room = ObjectDBFactory(
            db_key="StaffActorRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        other_room = ObjectDBFactory(
            db_key="StaffOtherRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.actor.location = actor_room
        self.actor.save()
        container = self._make_container(is_open=True)
        container.game_object.location = other_room
        container.game_object.save()
        self._put_in_container(container, "GoldCoin")
        action = LookAtItemAction()
        result = action.run(
            self.actor,
            container_id=container.game_object.pk,
            item_name="goldcoin",
        )
        self.assertTrue(result.success)
        self.assertIn("GoldCoin", result.message or "")
