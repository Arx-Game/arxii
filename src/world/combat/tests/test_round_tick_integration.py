"""Integration tests for round-tick condition processing in combat."""

from unittest.mock import patch

from evennia.utils.test_resources import EvenniaTestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import (
    EncounterStatus,
    ParticipantStatus,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.models import CombatRoundAction
from world.combat.services import begin_declaration_phase, resolve_round
from world.conditions.constants import DurationType
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.vitals.constants import CharacterStatus
from world.vitals.models import CharacterVitals


def _make_active_round_encounter():
    """Create a minimal encounter in DECLARING status with 1 active participant
    and 1 active opponent.

    The participant has a passives-only action (no technique) so resolve_round
    runs without needing the full magic pipeline.  The opponent has no threat
    pool entry and no NPC action, so no damage is dealt to the PC.
    """
    encounter = CombatEncounterFactory(
        status=EncounterStatus.DECLARING,
        round_number=1,
    )
    sheet = CharacterSheetFactory()
    participant = CombatParticipantFactory(
        encounter=encounter,
        character_sheet=sheet,
    )
    CharacterVitals.objects.create(
        character_sheet=sheet,
        health=100,
        max_health=100,
        status=CharacterStatus.ALIVE,
    )
    # Passives-only action — no focused_action, no focused_opponent_target.
    # This keeps the participant ACTIVE (not FLED) while making the round
    # resolve cleanly.
    CombatRoundAction.objects.create(
        participant=participant,
        round_number=1,
        focused_action=None,
        focused_opponent_target=None,
        is_ready=True,
    )
    # Opponent with no NPC action — skipped in _resolve_actions, stays ACTIVE.
    opponent = CombatOpponentFactory(
        encounter=encounter,
        health=50,
        max_health=50,
    )
    return encounter, participant, opponent


class RoundTickIntegrationTests(EvenniaTestCase):
    def test_end_of_round_decrements_condition_rounds(self) -> None:
        """After resolve_round, conditions on active participants should have
        their rounds_remaining decremented."""
        encounter, participant, _opponent = _make_active_round_encounter()

        # Apply a 3-round condition to the participant's character (ObjectDB).
        target = participant.character_sheet.character
        template = ConditionTemplateFactory(
            default_duration_type=DurationType.ROUNDS,
            default_duration_value=3,
        )
        instance = ConditionInstanceFactory(
            target=target,
            condition=template,
            rounds_remaining=3,
        )

        resolve_round(encounter)

        instance.refresh_from_db()
        self.assertEqual(instance.rounds_remaining, 2)

    def test_start_of_round_process_called_for_participants(self) -> None:
        """begin_declaration_phase should call process_round_start for each
        active participant's character."""
        # Set up an encounter in BETWEEN_ROUNDS so begin_declaration_phase
        # can advance it.
        encounter = CombatEncounterFactory(
            status=EncounterStatus.BETWEEN_ROUNDS,
            round_number=1,
        )
        sheet = CharacterSheetFactory()
        CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet,
            status=ParticipantStatus.ACTIVE,
        )
        CharacterVitals.objects.create(
            character_sheet=sheet,
            health=100,
            max_health=100,
            status=CharacterStatus.ALIVE,
        )
        # Need at least one active opponent for begin_declaration_phase to
        # proceed.
        CombatOpponentFactory(
            encounter=encounter,
            health=50,
            max_health=50,
        )

        with patch(
            "world.conditions.services.process_round_start",
        ) as mock_start:
            begin_declaration_phase(encounter)

        # process_round_start should have been called for the participant's
        # character ObjectDB (among any other calls for opponents).
        character = sheet.character
        mock_start.assert_any_call(character)

    def test_round_tick_runs_for_active_opponents(self) -> None:
        """Active opponents should also receive round-tick processing on their
        objectdb at end of round."""
        encounter, _participant, opponent = _make_active_round_encounter()

        # Apply a condition to the opponent's ObjectDB.
        template = ConditionTemplateFactory(
            default_duration_type=DurationType.ROUNDS,
            default_duration_value=3,
        )
        instance = ConditionInstanceFactory(
            target=opponent.objectdb,
            condition=template,
            rounds_remaining=3,
        )

        resolve_round(encounter)

        instance.refresh_from_db()
        self.assertEqual(instance.rounds_remaining, 2)

    def test_round_tick_skips_objectdbless_opponents(self) -> None:
        """If opp.objectdb is None (post-cleanup), the tick is skipped
        defensively without raising an error."""
        encounter, _participant, opponent = _make_active_round_encounter()

        # Simulate post-cleanup state: null out the objectdb FK.
        from world.combat.models import CombatOpponent

        CombatOpponent.objects.filter(pk=opponent.pk).update(objectdb=None)

        # Should not raise.
        resolve_round(encounter)


class RoundTickBeginDeclarationTests(EvenniaTestCase):
    """process_round_start fires at begin_declaration_phase for opponents."""

    def test_round_tick_runs_for_active_opponents_at_round_start(self) -> None:
        """Active opponents should receive process_round_start at begin of
        next round."""
        encounter = CombatEncounterFactory(
            status=EncounterStatus.BETWEEN_ROUNDS,
            round_number=1,
        )
        CombatOpponentFactory(
            encounter=encounter,
            health=50,
            max_health=50,
        )

        with patch("world.conditions.services.process_round_start") as mock_start:
            begin_declaration_phase(encounter)

        self.assertTrue(mock_start.called)
