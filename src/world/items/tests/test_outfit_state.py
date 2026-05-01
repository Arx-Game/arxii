"""Tests for OutfitState."""

from unittest.mock import MagicMock

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from flows.object_states.character_state import CharacterState
from flows.object_states.outfit_state import OutfitState
from world.character_sheets.factories import CharacterSheetFactory
from world.items.factories import (
    ItemInstanceFactory,
    ItemTemplateFactory,
    OutfitFactory,
)


class OutfitStateBuilder:
    """Helper to build a complete outfit + actor scenario per test."""

    def setUp(self) -> None:
        self.room = ObjectDBFactory(
            db_key=f"OutfitStateRoom_{id(self)}",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.character = ObjectDBFactory(
            db_key=f"OutfitStateChar_{id(self)}",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.sheet = CharacterSheetFactory(character=self.character)
        wardrobe_template = ItemTemplateFactory(
            name=f"OutfitStateWardrobe_{id(self)}",
            is_wardrobe=True,
            is_container=True,
        )
        wardrobe_obj = ObjectDBFactory(
            db_key=f"OutfitStateWardrobeObj_{id(self)}",
            db_typeclass_path="typeclasses.objects.Object",
            location=self.room,
        )
        self.wardrobe = ItemInstanceFactory(template=wardrobe_template, game_object=wardrobe_obj)
        self.outfit = OutfitFactory(
            character_sheet=self.sheet,
            wardrobe=self.wardrobe,
            name=f"OutfitStateLook_{id(self)}",
        )


class OutfitStateDefaultsTests(OutfitStateBuilder, TestCase):
    """OutfitState exposes can_apply + outfit + is_reachable_by."""

    def setUp(self) -> None:
        super().setUp()
        self.context = MagicMock()

    def test_outfit_property_returns_wrapped_obj(self) -> None:
        state = OutfitState(self.outfit, context=self.context)
        self.assertIs(state.outfit, self.outfit)

    def test_can_apply_default_true_with_no_actor(self) -> None:
        state = OutfitState(self.outfit, context=self.context)
        self.assertTrue(state.can_apply())

    def test_can_apply_with_reachable_actor_returns_true(self) -> None:
        state = OutfitState(self.outfit, context=self.context)
        actor_state = CharacterState(self.character, context=self.context)
        self.assertTrue(state.can_apply(actor=actor_state))

    def test_can_apply_with_actor_in_other_room_returns_false(self) -> None:
        other_room = ObjectDBFactory(
            db_key=f"OtherRoom_{id(self)}",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.character.location = other_room
        self.character.save()

        state = OutfitState(self.outfit, context=self.context)
        actor_state = CharacterState(self.character, context=self.context)
        self.assertFalse(state.can_apply(actor=actor_state))


class OutfitStateReachabilityTests(OutfitStateBuilder, TestCase):
    """is_reachable_by walks through the wardrobe ItemState."""

    def setUp(self) -> None:
        super().setUp()
        self.context = MagicMock()

    def test_wardrobe_in_actor_room_is_reachable(self) -> None:
        state = OutfitState(self.outfit, context=self.context)
        self.assertTrue(state.is_reachable_by(self.character))

    def test_wardrobe_in_other_room_is_not_reachable(self) -> None:
        other_room = ObjectDBFactory(
            db_key=f"OtherRoom2_{id(self)}",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.wardrobe.game_object.location = other_room
        self.wardrobe.game_object.save()

        state = OutfitState(self.outfit, context=self.context)
        self.assertFalse(state.is_reachable_by(self.character))


class OutfitStatePackageHookTests(OutfitStateBuilder, TestCase):
    """can_apply routes through _run_package_hook before falling back."""

    def setUp(self) -> None:
        super().setUp()
        self.context = MagicMock()

    def test_can_apply_denied_by_package_hook(self) -> None:
        state = OutfitState(self.outfit, context=self.context)
        package = MagicMock()

        def get_hook(name):
            if name == "can_apply":
                return lambda _owner, _pkg, _actor: False
            return None

        package.get_hook.side_effect = get_hook
        state.packages = [package]

        self.assertFalse(state.can_apply(actor=MagicMock()))
