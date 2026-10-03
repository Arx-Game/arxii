"""Tests for ``SendAwayAction`` (#4091, task 12): send a won-over NPC away.

Sending a charmed/turned/calmed NPC away ends the hold outright (R2, Decision 20) --
a named NPC is dropped off the map and has its allegiance condition lifted, and an
ephemeral nameless NPC is deleted via the shared ``delete_won_over_npc`` guard.
Covers the `Testing 11` cases from the task brief: the holder's own send-away, the
ephemeral-delete path, a non-holder's refusal, and that no allegiance-break check
is ever rolled by this action -- plus the task 12 fix round 1 rulings: the shared
presence predicate (the charmer must still be in the room), a failed ephemeral
delete falling back to the named-NPC path instead of lying about success, the
hold actually being removed (not just the body moved), and an NPC-only guard (a
PC carrying the actor's hold is refused, never matched by name) -- and fix round 2:
the NPC-only guard is offline-safe (an active ``RosterTenure``, not ``db_account``,
since Evennia clears ``db_account`` for an offline PC too).
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from actions.registry import get_action
from evennia_extensions.factories import AccountFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.combat.constants import OpponentStatus
from world.combat.factories import CombatEncounterFactory, CombatOpponentFactory
from world.conditions.constants import Allegiance
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.roster.factories import RosterEntryFactory, RosterTenureFactory


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
        self.charm = _charm("Send Away Charm")

        ConditionInstanceFactory(
            target=self.npc_char,
            condition=self.charm,
            source_character=self.wren,
            severity=4,
        )

    @patch("world.npc_services.allegiance_outcomes.attempt_allegiance_break")
    @patch("world.scenes.narrator.narrate_room_outcome")
    def test_send_away_drops_the_npc_lifts_the_hold_and_narrates_the_room(
        self, mock_narrate: object, mock_break: object
    ) -> None:
        result = get_action("send_away").run(actor=self.wren, target_persona_id=self.npc_persona.pk)

        self.assertTrue(result.success)
        self.npc_char.refresh_from_db()
        self.assertIsNone(self.npc_char.db_location)
        # Fix round 1 ruling 4: the hold really ends, not just the body moving.
        self.assertFalse(
            ConditionInstance.objects.filter(target=self.npc_char, condition=self.charm).exists()
        )
        mock_narrate.assert_called_once()
        mock_break.assert_not_called()

    def test_another_pcs_charm_refuses_with_a_message_and_changes_nothing(self) -> None:
        other = _character("Mirela", self.room)

        result = get_action("send_away").run(actor=other, target_persona_id=self.npc_persona.pk)

        self.assertFalse(result.success)
        self.assertIn("not under your sway", result.message)
        self.npc_char.refresh_from_db()
        self.assertEqual(self.npc_char.db_location_id, self.room.pk)
        self.assertTrue(
            ConditionInstance.objects.filter(target=self.npc_char, condition=self.charm).exists()
        )

    def test_no_charm_at_all_refuses_with_a_message(self) -> None:
        bystander = _character("Guard", self.room)
        # A wholly unheld target -- no condition sourced by anyone.
        unheld_char = _character("Loose Herald", self.room)
        unheld_persona = unheld_char.character_sheet.primary_persona

        result = get_action("send_away").run(actor=bystander, target_persona_id=unheld_persona.pk)

        self.assertFalse(result.success)
        self.assertIn("not under your sway", result.message)
        unheld_char.refresh_from_db()
        self.assertEqual(unheld_char.db_location_id, self.room.pk)

    def test_refuses_with_a_message_once_the_charmer_has_left_the_room(self) -> None:
        """Fix round 1 ruling 1: the shared presence predicate -- a hold alone
        isn't enough once the charmer is no longer co-located with the target."""
        elsewhere = _room()
        self.wren.location = elsewhere
        self.wren.save()

        result = get_action("send_away").run(actor=self.wren, target_persona_id=self.npc_persona.pk)

        self.assertFalse(result.success)
        self.assertIn("not here", result.message)
        self.npc_char.refresh_from_db()
        self.assertEqual(self.npc_char.db_location_id, self.room.pk)

    def test_pc_target_is_refused_as_not_an_npc(self) -> None:
        """Fix round 1 ruling 3: a PC carrying the actor's hold is refused, never
        matched by name. The canonical PC/NPC test is an active ``RosterTenure``
        (fix round 2) -- this PC is both actively puppeted (``db_account`` set)
        AND rostered, so it's refused either way; see the offline-PC test below
        for the case that actually distinguishes the two tests."""
        pc_char = _character("Lady Vance", self.room)
        pc_char.db_account = AccountFactory()
        entry = RosterEntryFactory(character_sheet=pc_char.character_sheet)
        RosterTenureFactory(roster_entry=entry)
        pc_persona = pc_char.character_sheet.primary_persona
        ConditionInstanceFactory(
            target=pc_char,
            condition=_charm("Send Away PC Guard Charm"),
            source_character=self.wren,
            severity=4,
        )

        result = get_action("send_away").run(actor=self.wren, target_persona_id=pc_persona.pk)

        self.assertFalse(result.success)
        self.assertIn("will of their own", result.message)
        pc_char.refresh_from_db()
        self.assertEqual(pc_char.db_location_id, self.room.pk)

    def test_offline_pc_with_active_tenure_is_refused_as_not_an_npc(self) -> None:
        """Fix round 2: ``db_account`` is also ``None`` for an OFFLINE PC (Evennia's
        ``unpuppet_object`` clears it the instant nobody is connected), so the
        canonical test must be an active ``RosterTenure``, not ``db_account``."""
        entry = RosterEntryFactory()
        pc_char = entry.character_sheet.character
        pc_char.location = self.room
        pc_char.save()
        RosterTenureFactory(roster_entry=entry)
        self.assertIsNone(pc_char.db_account)
        pc_persona = entry.character_sheet.primary_persona
        ConditionInstanceFactory(
            target=pc_char,
            condition=_charm("Send Away Offline PC Charm"),
            source_character=self.wren,
            severity=4,
        )

        result = get_action("send_away").run(actor=self.wren, target_persona_id=pc_persona.pk)

        self.assertFalse(result.success)
        self.assertIn("will of their own", result.message)
        pc_char.refresh_from_db()
        self.assertEqual(pc_char.db_location_id, self.room.pk)


class SendAwayEphemeralNPCTests(TestCase):
    """A nameless WON_OVER combat mook is deleted outright (``combat_opponent_id``)."""

    def setUp(self) -> None:
        self.enc = CombatEncounterFactory()
        self.wren = _character("Wren", self.enc.room)
        self.opponent = CombatOpponentFactory(
            encounter=self.enc, name="Lurking Foot", status=OpponentStatus.WON_OVER
        )
        self.charm = _charm("Send Away Nameless Charm")
        ConditionInstanceFactory(
            target=self.opponent.objectdb,
            condition=self.charm,
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

    def test_a_refused_delete_falls_back_to_dropping_and_unholding_the_npc(self) -> None:
        """Fix round 1 ruling 2: a failed ``delete_won_over_npc`` must not report
        a success that didn't happen -- it falls back to the named-NPC path."""
        objectdb = self.opponent.objectdb
        with (
            patch("world.combat.won_over.delete_won_over_npc", return_value=False),
            patch("world.scenes.narrator.narrate_room_outcome"),
        ):
            result = get_action("send_away").run(
                actor=self.wren, combat_opponent_id=self.opponent.pk
            )

        self.assertTrue(result.success)
        self.opponent.refresh_from_db()
        # The delete was refused -- the row still points at its ObjectDB.
        self.assertIsNotNone(self.opponent.objectdb_id)
        objectdb.refresh_from_db()
        self.assertIsNone(objectdb.db_location)
        self.assertFalse(
            ConditionInstance.objects.filter(target=objectdb, condition=self.charm).exists()
        )
