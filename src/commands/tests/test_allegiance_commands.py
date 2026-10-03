"""Tests for the telnet ``settle``/``sendaway``/``retain`` commands (#4091, tasks 8+12).

``CmdSettle`` is a bare ``ConsentRequestCommand`` shell (no pose text, R7) —
it opens the SAME ``create_action_request`` the web consent flow uses. These
tests mirror ``CmdIntimidateTests`` (``test_consent_commands.py``): a scene
with both characters in one room, then assert the dispatched command removes
the charm and the narrated settle line reaches the room (telnet parity).

``CmdSendAwayTests``/``CmdRetainTests`` (task 12) prove telnet reaches the
same ``send_away``/``charm_asset`` actions the persona menu and web dispatch
use — no new business logic lives in the commands.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.factories import (
    ActionTemplateFactory,
    ConsequencePoolEntryFactory,
    ConsequencePoolFactory,
)
from commands.allegiance import CmdRetain, CmdSendAway, CmdSettle
from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory, ConsequenceFactory
from world.checks.test_helpers import force_check_outcome
from world.conditions.constants import Allegiance
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.scenes.factories import SceneFactory
from world.traits.factories import CheckSystemSetupFactory


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


class CmdSendAwayTests(TestCase):
    """``sendaway <npc>`` reaches ``SendAwayAction`` (task 12, telnet parity)."""

    def setUp(self) -> None:
        self.room = ObjectDBFactory(db_key="Hall", db_typeclass_path="typeclasses.rooms.Room")
        self.initiator_char = ObjectDBFactory(
            db_key="Tamsin",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.target_char = ObjectDBFactory(
            db_key="Captain Hale",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        CharacterSheetFactory(character=self.initiator_char)
        CharacterSheetFactory(character=self.target_char)

        self.charm = ConditionTemplateFactory(
            name="Enthralled Sendaway Cmd",
            sets_allegiance=Allegiance.ALLY_OF_CASTER,
            allegiance_break_check_type=CheckTypeFactory(name="Allegiance Break Sendaway Cmd"),
        )
        ConditionInstanceFactory(
            target=self.target_char,
            condition=self.charm,
            source_character=self.initiator_char,
            severity=4,
        )

    def _run(self, caller: object, args: str) -> CmdSendAway:
        cmd = CmdSendAway()
        cmd.caller = caller
        cmd.args = args
        cmd.raw_string = f"sendaway {args}"
        caller.msg = MagicMock()
        cmd.func()
        return cmd

    def test_sendaway_reaches_the_action(self) -> None:
        with patch("world.scenes.narrator.narrate_room_outcome"):
            cmd = self._run(self.initiator_char, self.target_char.key)

        texts = _msg_texts(cmd.caller.msg)
        self.assertTrue(any("send" in text.lower() for text in texts))
        self.target_char.refresh_from_db()
        self.assertIsNone(self.target_char.db_location)


class CmdRetainTests(TestCase):
    """``retain <npc>=<role>`` reaches ``CharmAssetAction`` (task 12, telnet parity)."""

    def setUp(self) -> None:
        self.room = ObjectDBFactory(db_key="Hall", db_typeclass_path="typeclasses.rooms.Room")
        self.initiator_char = ObjectDBFactory(
            db_key="Tamsin",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.target_char = ObjectDBFactory(
            db_key="Captain Hale",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        CharacterSheetFactory(character=self.initiator_char)
        CharacterSheetFactory(character=self.target_char)

        self.charm = ConditionTemplateFactory(
            name="Enthralled Retain Cmd",
            sets_allegiance=Allegiance.ALLY_OF_CASTER,
            allegiance_break_check_type=CheckTypeFactory(name="Allegiance Break Retain Cmd"),
        )
        ConditionInstanceFactory(
            target=self.target_char,
            condition=self.charm,
            source_character=self.initiator_char,
            severity=4,
        )

    def _run(self, caller: object, args: str) -> CmdRetain:
        cmd = CmdRetain()
        cmd.caller = caller
        cmd.args = args
        cmd.raw_string = f"retain {args}"
        caller.msg = MagicMock()
        cmd.func()
        return cmd

    def test_retain_reaches_the_action(self) -> None:
        cmd = self._run(self.initiator_char, f"{self.target_char.key}=informant")

        texts = _msg_texts(cmd.caller.msg)
        self.assertTrue(any("charmed" in text.lower() for text in texts))

    def test_retain_accepts_hyphenated_personal_favor(self) -> None:
        cmd = self._run(self.initiator_char, f"{self.target_char.key}=personal-favor")

        texts = _msg_texts(cmd.caller.msg)
        self.assertTrue(any("charmed" in text.lower() for text in texts))
