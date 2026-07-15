"""Tests for SleepAction and extended WakeAction (#2290)."""

from django.test import TestCase

from world.character_sheets.services import create_character_with_sheet
from world.vitals.seeds import (
    ensure_dream_room,
    ensure_foundational_capabilities,
    ensure_sleeping_condition,
)
from world.vitals.services import perceives_dreamside


class SleepActionTests(TestCase):
    """Tests for SleepAction and extended WakeAction."""

    def setUp(self):
        ensure_foundational_capabilities()
        ensure_sleeping_condition()
        ensure_dream_room()
        self.char, self.sheet, _ = create_character_with_sheet(
            character_key="Sleeper",
            primary_persona_name="Sleeper",
        )

    def test_sleep_applies_sleeping_condition(self):
        from actions.definitions.dreams import SleepAction

        result = SleepAction().run(self.char)
        assert result.success
        assert perceives_dreamside(self.sheet) is True

    def test_wake_removes_sleeping(self):
        from actions.definitions.dreams import SleepAction
        from actions.definitions.vitals import WakeAction

        SleepAction().run(self.char)
        assert perceives_dreamside(self.sheet) is True
        result = WakeAction().run(self.char)
        assert result.success
        assert perceives_dreamside(self.sheet) is False

    def test_wake_when_already_awake(self):
        from actions.definitions.vitals import WakeAction

        result = WakeAction().run(self.char)
        assert not result.success
        assert "awake" in result.message.lower()
