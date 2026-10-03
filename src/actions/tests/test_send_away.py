"""Tests for ``SendAwayAction`` (#4091, task 12): send a won-over NPC away.

Sending a charmed/turned/calmed NPC away ends the hold outright (R2, Decision 20) --
a named NPC is dropped off the map, an ephemeral nameless NPC is deleted via the
shared ``delete_won_over_npc`` guard. Covers the `Testing 11` cases from the task
brief: the holder's own send-away, the ephemeral-delete path, a non-holder's
refusal, and that no allegiance-break check is ever rolled by this action.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from actions.registry import get_action
from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.combat.constants import OpponentStatus
from world.combat.factories import CombatEncounterFactory, CombatOpponentFactory
from world.conditions.constants import Allegiance
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory


def _room() -> object:
    return ObjectDBFactory(db_key="Hall", db_typeclass_path="typeclasses.rooms.Room")


def _character(key: str, location: object) -> object:
    char = ObjectDBFactory(
        db_key=key, db_typeclass_path="typeclasses.characters.Character", location=location
    )
    CharacterSheetFactory(character=char)
    return char


def _charm(name: str) -> object:
    return ConditionTemplateFactory(
        name=name,
        sets_allegiance=Allegiance.ALLY_OF_CASTER,
        allegiance_break_check_type=CheckTypeFactory(name=f"{name} break"),
    )


class SendAwayNamedNPCTests(TestCase):
    """A named NPC under the actor's own charm is sent away (dropped off the map)."""

    def setUp(self) -> None:
        self.room = _room()
        self.wren = _character("Wren", self.room)
        self.npc_char = _character("Captain Hale", self.room)
        self.npc_persona = self.npc_char.character_sheet.primary_persona

        ConditionInstanceFactory(
            target=self.npc_char,
            condition=_charm("Send Away Charm"),
            source_character=self.wren,
            severity=4,
        )

    @patch("world.npc_services.allegiance_outcomes.attempt_allegiance_break")
    @patch("world.scenes.narrator.narrate_room_outcome")
    def test_send_away_drops_the_npc_and_narrates_the_room(
        self, mock_narrate: object, mock_break: object
    ) -> None:
        result = get_action("send_away").run(actor=self.wren, target_persona_id=self.npc_persona.pk)

        self.assertTrue(result.success)
        self.npc_char.refresh_from_db()
        self.assertIsNone(self.npc_char.db_location)
        mock_narrate.assert_called_once()
        mock_break.assert_not_called()

    def test_another_pcs_charm_refuses_and_changes_nothing(self) -> None:
        other = _character("Mirela", self.room)

        result = get_action("send_away").run(actor=other, target_persona_id=self.npc_persona.pk)

        self.assertFalse(result.success)
        self.npc_char.refresh_from_db()
        self.assertEqual(self.npc_char.db_location_id, self.room.pk)

    def test_no_charm_at_all_refuses(self) -> None:
        bystander = _character("Guard", self.room)
        # A wholly unheld target -- no condition sourced by anyone.
        unheld_char = _character("Loose Herald", self.room)
        unheld_persona = unheld_char.character_sheet.primary_persona

        result = get_action("send_away").run(actor=bystander, target_persona_id=unheld_persona.pk)

        self.assertFalse(result.success)
        unheld_char.refresh_from_db()
        self.assertEqual(unheld_char.db_location_id, self.room.pk)


class SendAwayEphemeralNPCTests(TestCase):
    """A nameless WON_OVER combat mook is deleted outright (``combat_opponent_id``)."""

    def setUp(self) -> None:
        self.enc = CombatEncounterFactory()
        self.wren = _character("Wren", self.enc.room)
        self.opponent = CombatOpponentFactory(
            encounter=self.enc, name="Lurking Foot", status=OpponentStatus.WON_OVER
        )
        ConditionInstanceFactory(
            target=self.opponent.objectdb,
            condition=_charm("Send Away Nameless Charm"),
            source_character=self.wren,
            severity=4,
        )

    def test_send_away_deletes_the_ephemeral_npc(self) -> None:
        with patch("world.scenes.narrator.narrate_room_outcome"):
            result = get_action("send_away").run(
                actor=self.wren, combat_opponent_id=self.opponent.pk
            )

        self.assertTrue(result.success)
        self.opponent.refresh_from_db()
        self.assertIsNone(self.opponent.objectdb_id)
