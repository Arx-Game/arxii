"""Tests for the sneak/unsneak stance actions (#3288).

Journey coverage at the ``action.run()`` seam (telnet + web converge there):
per-room silent failure, the anti-spam token, the public in-place echo on
success, unsneak's reveal, and the arrival re-roll's two branches.
"""

from unittest.mock import patch

from django.test import TestCase

from actions.definitions.stealth import SneakAction, UnsneakAction
from evennia_extensions.factories import CharacterFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.conditions.factories import ConditionCategoryFactory, ConditionTemplateFactory
from world.stealth import services as stealth_services
from world.traits.factories import CheckOutcomeFactory


class StealthActionTestCase(TestCase):
    def setUp(self) -> None:
        self.room = RoomProfileFactory().objectdb
        self.char = CharacterFactory(db_key="prowler")
        CharacterSheetFactory(character=self.char)
        self.char.location = self.room
        self.char.save()
        CheckTypeFactory(name="Stealth")
        category = ConditionCategoryFactory(name="Concealed", conceals_from_perception=True)
        ConditionTemplateFactory(name="Concealed", category=category)
        self.success = CheckOutcomeFactory(name="Sneak-Success", success_level=1)
        self.failure = CheckOutcomeFactory(name="Sneak-Fail", success_level=0)


class SneakActionTests(StealthActionTestCase):
    def test_success_applies_stance_and_echoes_in_place(self):
        with (
            force_check_outcome(self.success),
            patch.object(self.room, "msg_contents") as mock_echo,
        ):
            result = SneakAction().run(actor=self.char)
        self.assertTrue(result.success)
        self.assertTrue(stealth_services.is_sneaking(self.char))
        # In-place success is a named, public echo — the room watched it happen.
        mock_echo.assert_called()

    def test_failure_is_silent_and_applies_nothing(self):
        with (
            force_check_outcome(self.failure),
            patch.object(self.room, "msg_contents") as mock_echo,
        ):
            result = SneakAction().run(actor=self.char)
        self.assertFalse(result.success)
        self.assertFalse(stealth_services.is_sneaking(self.char))
        mock_echo.assert_not_called()

    def test_same_room_retry_refuses_without_rolling(self):
        with force_check_outcome(self.failure):
            SneakAction().run(actor=self.char)
        with patch("world.stealth.services.roll_sneak") as mock_roll:
            result = SneakAction().run(actor=self.char)
        self.assertFalse(result.success)
        mock_roll.assert_not_called()

    def test_already_concealed_refuses(self):
        stealth_services.start_sneaking(self.char)
        with patch("world.stealth.services.roll_sneak") as mock_roll:
            result = SneakAction().run(actor=self.char)
        self.assertFalse(result.success)
        mock_roll.assert_not_called()


class UnsneakActionTests(StealthActionTestCase):
    def test_unsneak_reveals_publicly(self):
        stealth_services.start_sneaking(self.char)
        with patch.object(self.room, "msg_contents") as mock_echo:
            result = UnsneakAction().run(actor=self.char)
        self.assertTrue(result.success)
        self.assertFalse(stealth_services.is_sneaking(self.char))
        mock_echo.assert_called()

    def test_unsneak_while_visible_is_a_noop_message(self):
        result = UnsneakAction().run(actor=self.char)
        self.assertFalse(result.success)

    def test_unsneak_leaves_magical_concealment_alone(self):
        """Instance-scoped strip: a non-sneak concealment isn't unsneak's to remove."""
        from world.conditions.models import ConditionTemplate
        from world.conditions.services import apply_condition, is_concealed

        template = ConditionTemplate.objects.get(name="Concealed")
        apply_condition(target=self.char, condition=template, source_description="magic")
        result = UnsneakAction().run(actor=self.char)
        self.assertFalse(result.success)
        self.assertTrue(is_concealed(self.char))


class ArrivalRerollTests(StealthActionTestCase):
    def test_passed_reroll_keeps_stance(self):
        stealth_services.start_sneaking(self.char)
        with force_check_outcome(self.success):
            still_hidden = stealth_services.reroll_on_arrival(self.char)
        self.assertTrue(still_hidden)
        self.assertTrue(stealth_services.is_sneaking(self.char))

    def test_failed_reroll_strips_quietly(self):
        stealth_services.start_sneaking(self.char)
        with (
            force_check_outcome(self.failure),
            patch.object(self.room, "msg_contents") as mock_echo,
        ):
            still_hidden = stealth_services.reroll_on_arrival(self.char)
        self.assertFalse(still_hidden)
        self.assertFalse(stealth_services.is_sneaking(self.char))
        # Silent failure: no attempt echo of any kind.
        mock_echo.assert_not_called()

    def test_visible_character_is_a_noop(self):
        with patch("world.stealth.services.roll_sneak") as mock_roll:
            self.assertFalse(stealth_services.reroll_on_arrival(self.char))
        mock_roll.assert_not_called()
