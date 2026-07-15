"""Tests for DreamwalkAction and the escape lever (#2290)."""

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.services import create_character_with_sheet
from world.conditions.models import ConditionTemplate
from world.conditions.services import apply_condition
from world.vitals.constants import SLEEPING_CONDITION_NAME
from world.vitals.seeds import (
    ensure_dream_room,
    ensure_foundational_capabilities,
    ensure_sleeping_condition,
)


class DreamwalkActionTests(TestCase):
    """Tests for DreamwalkAction and the escape lever."""

    def setUp(self):
        ensure_foundational_capabilities()
        ensure_sleeping_condition()
        ensure_dream_room()

        self.char_room = ObjectDBFactory(db_key="Char Room")
        self.target_room = ObjectDBFactory(db_key="Target Room")
        self.char, self.sheet, _ = create_character_with_sheet(
            character_key="Dreamwalker",
            primary_persona_name="Dreamwalker",
        )
        self.target_char, self.target_sheet, _ = create_character_with_sheet(
            character_key="Target",
            primary_persona_name="Target",
        )
        # Place them in different rooms
        self.char.location = self.char_room
        self.char.save()
        self.target_char.location = self.target_room
        self.target_char.save()
        self.template = ConditionTemplate.objects.get(name=SLEEPING_CONDITION_NAME)
        apply_condition(target=self.char, condition=self.template)
        apply_condition(target=self.target_char, condition=self.template)

    def test_dreamwalk_rejects_no_thread(self):
        from actions.definitions.dreams import DreamwalkAction

        result = DreamwalkAction().run(self.char, target=self.target_char)
        assert not result.success
        assert "bond" in result.message.lower()

    def test_dreamwalk_rejects_when_not_dreaming(self):
        from actions.definitions.dreams import DreamwalkAction
        from world.conditions.services import remove_condition

        remove_condition(self.char, self.template)
        result = DreamwalkAction().run(self.char, target=self.target_char)
        assert not result.success
        assert "dream" in result.message.lower()

    def test_dreamwalk_rejects_target_not_dreaming(self):
        from actions.definitions.dreams import DreamwalkAction
        from world.conditions.services import remove_condition

        remove_condition(self.target_char, self.template)
        result = DreamwalkAction().run(self.char, target=self.target_char)
        assert not result.success
        assert "not dreaming" in result.message.lower() or "dream" in result.message.lower()
