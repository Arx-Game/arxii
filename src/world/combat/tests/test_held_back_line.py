"""The round names who held back under TIMED/MANUAL pace (#3552)."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import OpponentTier, PaceMode, ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.models import CombatRoundAction
from world.combat.services import resolve_round
from world.scenes.constants import RoundStatus
from world.vitals.models import CharacterVitals


def _make_encounter(pace_mode: str):
    encounter = CombatEncounterFactory(
        status=RoundStatus.DECLARING,
        pace_mode=pace_mode,
        round_number=1,
    )
    CombatOpponentFactory(encounter=encounter, tier=OpponentTier.MOOK)
    return encounter


def _add_pc(encounter, name: str):
    sheet = CharacterSheetFactory(character__db_key=name)
    CharacterVitals.objects.create(character_sheet=sheet, health=100, max_health=100)
    return CombatParticipantFactory(
        encounter=encounter, character_sheet=sheet, status=ParticipantStatus.ACTIVE
    )


def _declare_passive(participant) -> CombatRoundAction:
    return CombatRoundAction.objects.create(
        participant=participant,
        round_number=participant.encounter.round_number,
        is_ready=True,
    )


class HeldBackLineTests(TestCase):
    def _resolve_capturing(self, encounter) -> list[str]:
        with patch.object(encounter.room, "msg_contents") as mock_msg:
            resolve_round(encounter)
        return [c.args[0] for c in mock_msg.call_args_list]

    def test_manual_pace_names_the_silent_participant(self) -> None:
        encounter = _make_encounter(PaceMode.MANUAL)
        acted = _add_pc(encounter, "Aerande")
        _add_pc(encounter, "Brannoc")
        _declare_passive(acted)
        sent = self._resolve_capturing(encounter)
        self.assertIn("Brannoc holds back.", sent)
        self.assertNotIn("Aerande holds back.", sent)

    def test_timed_pace_names_the_silent_participant(self) -> None:
        encounter = _make_encounter(PaceMode.TIMED)
        _add_pc(encounter, "Brannoc")
        sent = self._resolve_capturing(encounter)
        self.assertIn("Brannoc holds back.", sent)

    def test_ready_pace_is_silent(self) -> None:
        encounter = _make_encounter(PaceMode.READY)
        _add_pc(encounter, "Brannoc")
        sent = self._resolve_capturing(encounter)
        self.assertNotIn("Brannoc holds back.", sent)
