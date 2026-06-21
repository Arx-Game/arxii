"""Tests for declare_interpose service function, serializer, and view action (#1273)."""

from django.test import TestCase
import pytest

from world.combat.constants import CombatManeuver, EncounterStatus, ParticipantStatus
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.services import declare_interpose
from world.vitals.models import CharacterVitals


class DeclareInterposeServiceTest(TestCase):
    """Tests for the declare_interpose service function."""

    def setUp(self) -> None:
        super().setUp()
        self.encounter = CombatEncounterFactory(status=EncounterStatus.DECLARING, round_number=1)
        self.participant = CombatParticipantFactory(encounter=self.encounter)
        self.ally = CombatParticipantFactory(encounter=self.encounter)
        CharacterVitals.objects.create(
            character_sheet=self.participant.character_sheet, health=50, max_health=100
        )
        CharacterVitals.objects.create(
            character_sheet=self.ally.character_sheet, health=50, max_health=100
        )

    def test_interpose_sets_maneuver_and_ally(self) -> None:
        """declare_interpose creates an action with maneuver=INTERPOSE and is_ready=True."""
        action = declare_interpose(self.participant, self.ally)
        assert action.maneuver == CombatManeuver.INTERPOSE
        assert action.focused_ally_target == self.ally
        assert action.is_ready is True
        self.participant.refresh_from_db()
        assert self.participant.status == ParticipantStatus.ACTIVE

    def test_interpose_ally_none_guards_any_ally(self) -> None:
        """declare_interpose(participant, None) sets ally target to None — guard any ally."""
        action = declare_interpose(self.participant, None)
        assert action.maneuver == CombatManeuver.INTERPOSE
        assert action.focused_ally_target is None
        assert action.is_ready is True

    def test_interpose_rejects_outside_declaring(self) -> None:
        """Cannot interpose outside DECLARING status."""
        self.encounter.status = EncounterStatus.BETWEEN_ROUNDS
        self.encounter.save(update_fields=["status"])
        with pytest.raises(ValueError, match="expected 'Declaring'"):
            declare_interpose(self.participant, self.ally)

    def test_interpose_rejects_inactive_participant(self) -> None:
        """A participant who has fled cannot declare interpose."""
        self.participant.status = ParticipantStatus.FLED
        self.participant.save(update_fields=["status"])
        with pytest.raises(ValueError, match="no longer active"):
            declare_interpose(self.participant, self.ally)

    def test_interpose_rejects_self(self) -> None:
        """Cannot interpose for yourself."""
        with pytest.raises(ValueError, match="Cannot interpose yourself"):
            declare_interpose(self.participant, self.participant)

    def test_interpose_rejects_foreign_or_inactive_ally(self) -> None:
        """Ally must be active and in the same encounter when specified."""
        # Inactive ally (FLED) in same encounter
        self.ally.status = ParticipantStatus.FLED
        self.ally.save(update_fields=["status"])
        with pytest.raises(ValueError, match="active participant in this encounter"):
            declare_interpose(self.participant, self.ally)

        # Foreign encounter ally
        other_encounter = CombatEncounterFactory(status=EncounterStatus.DECLARING, round_number=1)
        foreign_ally = CombatParticipantFactory(encounter=other_encounter)
        CharacterVitals.objects.create(
            character_sheet=foreign_ally.character_sheet, health=50, max_health=100
        )
        with pytest.raises(ValueError, match="active participant in this encounter"):
            declare_interpose(self.participant, foreign_ally)

    def test_interpose_ally_none_skips_self_check(self) -> None:
        """ally=None does not raise even though no ally id is given (no self-check runs)."""
        # No ValueError expected — this is just a smoke test for the None path
        action = declare_interpose(self.participant, None)
        assert action.maneuver == CombatManeuver.INTERPOSE
