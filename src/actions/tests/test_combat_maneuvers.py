"""Tests for combat maneuver actions (#1453, #1452).

These drive the actions through ``Action.run()`` — the same lifecycle the telnet
command and web viewset reach via ``dispatch_player_action`` — so they cover the
full shared seam, not just the service call.
"""

from __future__ import annotations

from django.test import TestCase

from actions.definitions.combat_maneuvers import FleeAction
from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import CombatManeuver, EncounterStatus, ParticipantStatus
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.models import CombatRoundAction
from world.vitals.models import CharacterVitals


class CombatManeuverActionTestBase(TestCase):
    """Shared fixture: a player character active in a DECLARING encounter."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory(db_key="maneuverchar")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        cls.participant = CombatParticipantFactory(
            encounter=cls.encounter,
            character_sheet=cls.sheet,
            status=ParticipantStatus.ACTIVE,
        )
        CharacterVitals.objects.get_or_create(
            character_sheet=cls.sheet,
            defaults={"health": 50, "max_health": 100},
        )


class FleeActionTest(CombatManeuverActionTestBase):
    def test_flee_declares_flee_maneuver(self) -> None:
        result = FleeAction().run(self.character)
        self.assertTrue(result.success, result.message)
        action = CombatRoundAction.objects.get(
            participant=self.participant,
            round_number=self.encounter.round_number,
        )
        self.assertEqual(action.maneuver, CombatManeuver.FLEE)

    def test_flee_fails_when_not_in_combat(self) -> None:
        loner = CharacterFactory(db_key="lonerchar")
        CharacterSheetFactory(character=loner)
        result = FleeAction().run(loner)
        self.assertFalse(result.success)
