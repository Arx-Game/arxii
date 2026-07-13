"""Tests for dreamside perception while unconscious (#2287)."""

from django.test import TestCase

from actions.definitions.perception import LookAction
from flows.service_functions.communication import _dreamside_occupants
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.constants import UNCONSCIOUS_CONDITION_NAME
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.vitals.constants import DREAM_ROOM_KEY, CharacterLifeState
from world.vitals.factories import CharacterVitalsFactory
from world.vitals.seeds import ensure_dream_room
from world.vitals.services import get_dream_room, perceives_dreamside


class PerceivesDreamsideTests(TestCase):
    """Unconscious relocates perception; death always wins (ghosts watch)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.vitals = CharacterVitalsFactory(character_sheet=cls.sheet)
        cls.unconscious = ConditionTemplateFactory(name=UNCONSCIOUS_CONDITION_NAME)

    def test_conscious_character_is_not_dreamside(self) -> None:
        self.assertFalse(perceives_dreamside(self.sheet))

    def test_unconscious_character_is_dreamside(self) -> None:
        ConditionInstanceFactory(target=self.sheet.character, condition=self.unconscious)
        self.assertTrue(perceives_dreamside(self.sheet))

    def test_dead_character_is_never_dreamside(self) -> None:
        ConditionInstanceFactory(target=self.sheet.character, condition=self.unconscious)
        self.vitals.life_state = CharacterLifeState.DEAD
        self.vitals.save(update_fields=["life_state"])
        self.assertFalse(perceives_dreamside(self.sheet))

    def test_none_sheet_is_not_dreamside(self) -> None:
        self.assertFalse(perceives_dreamside(None))


class DreamRoomTests(TestCase):
    """Dream-room lookup and the look-substitution seam."""

    def test_unseeded_returns_none(self) -> None:
        self.assertIsNone(get_dream_room())

    def test_seeded_room_is_found(self) -> None:
        room = ensure_dream_room()
        self.assertEqual(get_dream_room().pk, room.pk)

    def test_unconscious_look_shows_dream_room(self) -> None:
        from evennia.utils import create as evennia_create

        ensure_dream_room()
        sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=sheet)
        unconscious = ConditionTemplateFactory(name=UNCONSCIOUS_CONDITION_NAME)
        character = sheet.character
        waking_room = evennia_create.create_object(
            typeclass="typeclasses.rooms.Room", key="Waking Room", nohome=True
        )
        character.location = waking_room

        conscious_view = LookAction().run(actor=character, target=waking_room)
        self.assertIn("Waking Room", conscious_view.message)

        ConditionInstanceFactory(target=character, condition=unconscious)
        dream_view = LookAction().run(actor=character, target=waking_room)
        self.assertIn(DREAM_ROOM_KEY, dream_view.message)


class DreamsideMessageGateTests(TestCase):
    """Room broadcasts skip dreamside occupants; ghosts still receive."""

    def test_dreamside_occupants_excludes_only_unconscious(self) -> None:
        from evennia.utils import create as evennia_create

        room = evennia_create.create_object(
            typeclass="typeclasses.rooms.Room", key="Common Room", nohome=True
        )
        unconscious_template = ConditionTemplateFactory(name=UNCONSCIOUS_CONDITION_NAME)

        sleeper_sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=sleeper_sheet)
        sleeper = sleeper_sheet.character
        sleeper.location = room
        ConditionInstanceFactory(target=sleeper, condition=unconscious_template)

        ghost_sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=ghost_sheet, life_state=CharacterLifeState.DEAD)
        ghost = ghost_sheet.character
        ghost.location = room

        bystander_sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=bystander_sheet)
        bystander = bystander_sheet.character
        bystander.location = room

        excluded = _dreamside_occupants(room)
        self.assertEqual([obj.pk for obj in excluded], [sleeper.pk])
        self.assertNotIn(ghost.pk, [obj.pk for obj in excluded])
        self.assertNotIn(bystander.pk, [obj.pk for obj in excluded])
