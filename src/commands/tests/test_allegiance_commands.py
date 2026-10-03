"""Tests for the telnet ``settle`` command (#4091, task 8).

``CmdSettle`` is a bare ``ConsentRequestCommand`` shell (no pose text, R7) —
it opens the SAME ``create_action_request`` the web consent flow uses. These
tests mirror ``CmdIntimidateTests`` (``test_consent_commands.py``): a scene
with both characters in one room, then assert the dispatched command removes
the charm and the narrated settle line reaches the room (telnet parity).
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from actions.factories import (
    ActionTemplateFactory,
    ConsequencePoolEntryFactory,
    ConsequencePoolFactory,
)
from commands.allegiance import CmdSettle
from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory, ConsequenceFactory
from world.checks.test_helpers import force_check_outcome
from world.conditions.constants import Allegiance
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.scenes.factories import SceneFactory
from world.traits.factories import CheckSystemSetupFactory


class CmdSettleTests(TestCase):
    """``settle <npc>`` removes the charm and narrates the room (telnet parity)."""

    def setUp(self) -> None:
        # Evennia ObjectDB fixtures must be built in setUp, not setUpTestData:
        # the idmapper's DbHolder is un-deepcopyable, so the classmethod
        # snapshot machinery raises copy.Error (the DbHolder setUpTestData trap).
        self.room = ObjectDBFactory(
            db_key="Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.initiator_char = ObjectDBFactory(
            db_key="Tamsin",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.target_char = ObjectDBFactory(
            db_key="Enthralled Herald",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.initiator_sheet = CharacterSheetFactory(character=self.initiator_char)
        self.target_sheet = CharacterSheetFactory(character=self.target_char)
        self.initiator_persona = self.initiator_sheet.primary_persona
        self.target_persona = self.target_sheet.primary_persona
        self.scene = SceneFactory(is_active=True, location=self.room)
        if hasattr(self.room, "_active_scene_cache"):
            del self.room._active_scene_cache

        ActionTemplateFactory(name="Settle a charm", category="social", settles_allegiance=True)
        self.enthralled = ConditionTemplateFactory(
            name="Enthralled Settle Cmd",
            sets_allegiance=Allegiance.ALLY_OF_CASTER,
            allegiance_break_check_type=CheckTypeFactory(name="Allegiance Break Cmd"),
            settle_consequence_pool=None,
        )
        self.instance = ConditionInstanceFactory(
            target=self.target_char,
            condition=self.enthralled,
            severity=4,
        )

    def _run(self, caller: object, args: str) -> CmdSettle:
        cmd = CmdSettle()
        cmd.caller = caller
        cmd.args = args
        cmd.raw_string = f"settle {args}"
        caller.msg = MagicMock()
        cmd.func()
        return cmd

    @staticmethod
    def _msg_texts(mock_msg: MagicMock) -> list[str]:
        """Flatten every ``.msg(...)`` call's text, whichever calling convention.

        ``Object.msg_contents`` calls each recipient's ``.msg(text=(str, {}),
        ...)`` (keyword, text wrapped in an outcmd tuple); ``ArxCommand.msg``
        calls ``self.caller.msg(text)`` (positional, bare string).
        """
        texts: list[str] = []
        for call in mock_msg.call_args_list:
            text = call.kwargs.get("text")
            if text is None and call.args:
                text = call.args[0]
            if isinstance(text, tuple):
                text = text[0]
            if text is not None:
                texts.append(str(text))
        return texts

    def test_settle_removes_the_charm_and_narrates_the_room(self) -> None:
        self._run(self.initiator_char, self.target_char.key)

        self.assertFalse(ConditionInstance.objects.filter(pk=self.instance.pk).exists())
        texts = self._msg_texts(self.initiator_char.msg)
        self.assertTrue(any(self.enthralled.name in text for text in texts))

    def test_no_args_reports_error_and_removes_nothing(self) -> None:
        cmd = self._run(self.initiator_char, "")

        self.assertTrue(ConditionInstance.objects.filter(pk=self.instance.pk).exists())
        cmd.caller.msg.assert_called()

    def test_settle_narrates_the_authored_consequence_label(self) -> None:
        """A settle pool's authored success label reaches the room verbatim."""
        outcomes = CheckSystemSetupFactory.create()["outcomes"]
        pool = ConsequencePoolFactory(name="Settle Cmd authored pool")
        authored_label = "The spell breaks, and she blinks, herself again."
        success_row = ConsequenceFactory(outcome_tier=outcomes["success"], label=authored_label)
        ConsequencePoolEntryFactory(pool=pool, consequence=success_row)
        labeled_condition = ConditionTemplateFactory(
            name="Enthralled Settle Cmd Labeled",
            sets_allegiance=Allegiance.ALLY_OF_CASTER,
            allegiance_break_check_type=CheckTypeFactory(name="Allegiance Break Cmd Labeled"),
            settle_consequence_pool=pool,
        )
        # Settle the labeled charm instead of self.instance, so only one
        # allegiance condition is active on the target.
        self.instance.delete()
        instance = ConditionInstanceFactory(
            target=self.target_char,
            condition=labeled_condition,
            severity=4,
        )

        with force_check_outcome(outcomes["success"]):
            self._run(self.initiator_char, self.target_char.key)

        self.assertFalse(ConditionInstance.objects.filter(pk=instance.pk).exists())
        texts = self._msg_texts(self.initiator_char.msg)
        self.assertTrue(any(authored_label in text for text in texts))
