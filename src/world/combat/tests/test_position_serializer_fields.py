"""Tests for current_position fields on ParticipantSerializer and OpponentSerializer (#532).

A placed participant/opponent serializes ``current_position`` as ``{"id": ..., "name": ...}``;
an unplaced one (no ObjectPosition row) serializes it as ``None``.

Built in ``setUp`` rather than ``setUpTestData``: the factories create Evennia ObjectDB
instances (DbHolder — not deepcopyable), which would break ``setUpTestData``'s deepcopy.
"""

from __future__ import annotations

from django.test import TestCase

from world.areas.positioning.factories import PositionFactory
from world.areas.positioning.services import place_in_position
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.serializers import OpponentSerializer, ParticipantSerializer


class ParticipantPositionSerializerTests(TestCase):
    """current_position on ParticipantSerializer (#532)."""

    def setUp(self) -> None:
        super().setUp()
        from evennia import create_object

        from world.character_sheets.factories import CharacterSheetFactory

        # Create a shared room for both the encounter and the position.
        self.room = create_object("typeclasses.rooms.Room", key="Pos Ser Test Room", nohome=True)
        self.position = PositionFactory(room=self.room, name="balcony")

        # Build a participant whose character lives in that room.
        self.sheet = CharacterSheetFactory()
        self.sheet.character.location = self.room
        self.sheet.character.save()

        encounter = CombatEncounterFactory(room=self.room)
        self.participant = CombatParticipantFactory(encounter=encounter, character_sheet=self.sheet)

    def test_placed_participant_serializes_current_position(self) -> None:
        """A participant in a position returns {id, name} for current_position."""
        place_in_position(self.sheet.character, self.position)
        # Fresh instance to avoid stale cached_property.
        from world.combat.models import CombatParticipant

        fresh = CombatParticipant.objects.get(pk=self.participant.pk)
        data = ParticipantSerializer(fresh).data
        self.assertEqual(
            data["current_position"],
            {"id": self.position.id, "name": self.position.name},
        )

    def test_unplaced_participant_serializes_current_position_as_none(self) -> None:
        """A participant not in any position returns None for current_position."""
        from world.combat.models import CombatParticipant

        fresh = CombatParticipant.objects.get(pk=self.participant.pk)
        data = ParticipantSerializer(fresh).data
        self.assertIsNone(data["current_position"])


class OpponentPositionSerializerTests(TestCase):
    """current_position on OpponentSerializer (#532)."""

    def setUp(self) -> None:
        super().setUp()
        from evennia import create_object

        # Create a shared room for both the encounter and the position.
        self.room = create_object("typeclasses.rooms.Room", key="Opp Pos Ser Room", nohome=True)
        self.position = PositionFactory(room=self.room, name="front_line")

        encounter = CombatEncounterFactory(room=self.room)
        # Factory places the NPC in the encounter's room automatically.
        self.opponent = CombatOpponentFactory(encounter=encounter)

    def test_placed_opponent_serializes_current_position(self) -> None:
        """An opponent whose ObjectDB is in a position returns {id, name}."""
        from world.combat.models import CombatOpponent

        # The opponent's objectdb was created in the encounter room; place it.
        fresh_opp = CombatOpponent.objects.get(pk=self.opponent.pk)
        npc_obj = fresh_opp.objectdb
        place_in_position(npc_obj, self.position)

        # Fresh again to bust cached_property.
        fresh2 = CombatOpponent.objects.get(pk=self.opponent.pk)
        data = OpponentSerializer(fresh2).data
        self.assertEqual(
            data["current_position"],
            {"id": self.position.id, "name": self.position.name},
        )

    def test_unplaced_opponent_serializes_current_position_as_none(self) -> None:
        """An opponent with no ObjectPosition row returns None."""
        from world.combat.models import CombatOpponent

        fresh = CombatOpponent.objects.get(pk=self.opponent.pk)
        data = OpponentSerializer(fresh).data
        self.assertIsNone(data["current_position"])

    def test_ephemeral_opponent_without_objectdb_serializes_none(self) -> None:
        """An opponent with objectdb_id=None (ephemeral, destroyed NPC) returns None."""
        from world.combat.models import CombatOpponent

        encounter = CombatEncounterFactory()
        # Directly create an opponent with no backing ObjectDB.
        opp = CombatOpponent.objects.create(
            encounter=encounter,
            name="Ghost Mook",
            health=10,
            max_health=10,
            objectdb_id=None,
            objectdb_is_ephemeral=True,
        )
        data = OpponentSerializer(opp).data
        self.assertIsNone(data["current_position"])
