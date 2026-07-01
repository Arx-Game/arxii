"""Tests for declare_succor service function (#1744)."""

from django.test import TestCase
import pytest

from world.combat.constants import CombatManeuver, ParticipantStatus
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.services import declare_succor
from world.scenes.constants import RoundStatus
from world.vitals.models import CharacterVitals


class DeclareSuccorServiceTest(TestCase):
    """Tests for the declare_succor service function."""

    def setUp(self) -> None:
        super().setUp()
        self.encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
        self.succorer = CombatParticipantFactory(encounter=self.encounter)
        self.ally = CombatParticipantFactory(encounter=self.encounter)
        CharacterVitals.objects.create(
            character_sheet=self.succorer.character_sheet, health=50, max_health=100
        )
        CharacterVitals.objects.create(
            character_sheet=self.ally.character_sheet, health=50, max_health=100
        )

    def test_declare_succor_writes_round_action(self) -> None:
        action = declare_succor(self.succorer, self.ally)
        assert action.maneuver == CombatManeuver.SUCCOR
        assert action.focused_ally_target_id == self.ally.pk
        assert action.is_ready is True
        assert action.succor_resolution is None

    def test_cannot_succor_self(self) -> None:
        with pytest.raises(ValueError, match="Cannot succor yourself"):
            declare_succor(self.succorer, self.succorer)

    def test_succor_rejects_outside_declaring(self) -> None:
        self.encounter.status = RoundStatus.BETWEEN_ROUNDS
        self.encounter.save(update_fields=["status"])
        with pytest.raises(ValueError, match="expected 'Declaring'"):
            declare_succor(self.succorer, self.ally)

    def test_succor_rejects_inactive_participant(self) -> None:
        self.succorer.status = ParticipantStatus.FLED
        self.succorer.save(update_fields=["status"])
        with pytest.raises(ValueError, match="no longer active"):
            declare_succor(self.succorer, self.ally)

    def test_succor_rejects_foreign_or_inactive_ally(self) -> None:
        self.ally.status = ParticipantStatus.FLED
        self.ally.save(update_fields=["status"])
        with pytest.raises(ValueError, match="active participant in this encounter"):
            declare_succor(self.succorer, self.ally)

        other_encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
        foreign_ally = CombatParticipantFactory(encounter=other_encounter)
        CharacterVitals.objects.create(
            character_sheet=foreign_ally.character_sheet, health=50, max_health=100
        )
        with pytest.raises(ValueError, match="active participant in this encounter"):
            declare_succor(self.succorer, foreign_ally)
