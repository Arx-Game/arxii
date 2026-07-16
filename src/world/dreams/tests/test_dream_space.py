"""Tests for dream space resolution and dreamside perception (#2290)."""

from django.test import TestCase
from evennia.objects.models import ObjectDB

from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.services import create_character_with_sheet
from world.conditions.models import ConditionTemplate
from world.conditions.services import apply_condition
from world.dreams.models import DreamReflection
from world.dreams.services import get_dream_space
from world.vitals.constants import SLEEPING_CONDITION_NAME
from world.vitals.seeds import (
    ensure_dream_room,
    ensure_foundational_capabilities,
    ensure_sleeping_condition,
)
from world.vitals.services import get_dream_room, perceives_dreamside


class GetDreamSpaceTests(TestCase):
    """Tests for get_dream_space() resolution."""

    def setUp(self):
        ensure_dream_room()

    def test_returns_reflection_dream_room_when_exists(self):
        waking = ObjectDBFactory(db_key="Waking Room")
        dream = ObjectDBFactory(db_key="Dream Room")
        DreamReflection.objects.create(waking_room=waking, dream_room=dream)
        result = get_dream_space(room=waking)
        assert result == dream

    def test_falls_back_to_liminal_when_no_reflection(self):
        room = ObjectDBFactory(db_key="No Reflection")
        result = get_dream_space(room=room)
        assert result == get_dream_room()

    def test_falls_back_to_none_when_unseeded(self):
        room = ObjectDBFactory(db_key="Unseeded Room")
        # Delete the liminal room to simulate unseeded state
        from world.vitals.constants import DREAM_ROOM_TAG, DREAM_ROOM_TAG_CATEGORY

        for r in ObjectDB.objects.filter(
            db_tags__db_key=DREAM_ROOM_TAG, db_tags__db_category=DREAM_ROOM_TAG_CATEGORY
        ):
            r.delete()
        result = get_dream_space(room=room)
        assert result is None


class PerceivesDreamsideSleepingTests(TestCase):
    """Tests that Sleeping characters perceive dreamside."""

    def setUp(self):
        ensure_foundational_capabilities()
        ensure_sleeping_condition()
        self.char, self.sheet, _ = create_character_with_sheet(
            character_key="Sleeper",
            primary_persona_name="Sleeper",
        )
        self.template = ConditionTemplate.objects.get(name=SLEEPING_CONDITION_NAME)

    def test_conscious_character_is_not_dreamside(self):
        assert perceives_dreamside(self.sheet) is False

    def test_sleeping_character_perceives_dreamside(self):
        apply_condition(target=self.char, condition=self.template)
        assert perceives_dreamside(self.sheet) is True

    def test_dead_character_is_never_dreamside(self):
        from world.vitals.constants import CharacterLifeState
        from world.vitals.models import CharacterVitals

        apply_condition(target=self.char, condition=self.template)
        CharacterVitals.objects.create(
            character_sheet=self.sheet,
            life_state=CharacterLifeState.DEAD,
        )
        assert perceives_dreamside(self.sheet) is False
