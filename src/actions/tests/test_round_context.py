"""Tests for the combat-agnostic RoundContext seam.

Covers:
- get_active_round_context returns None for a character with no active combat participation.
- Returns a RoundContext with is_declaration_open=True when character is ACTIVE in a
  DECLARING encounter.
- is_declaration_open is False when encounter status is not DECLARING (e.g. RESOLVING).
- round_id returns the expected (encounter_id, round_number) tuple.
"""

import django.test

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import EncounterStatus, ParticipantStatus
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory


class TestGetActiveRoundContextNoParticipation(django.test.TestCase):
    """Character with no combat participation → returns None."""

    def test_no_participation_returns_none(self) -> None:
        sheet = CharacterSheetFactory()
        from actions.round_context import get_active_round_context

        result = get_active_round_context(sheet)
        self.assertIsNone(result)


class TestGetActiveRoundContextDeclaring(django.test.TestCase):
    """Character ACTIVE in a DECLARING encounter → is_declaration_open=True."""

    def setUp(self) -> None:
        self.encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        self.participant = CombatParticipantFactory(
            encounter=self.encounter,
            status=ParticipantStatus.ACTIVE,
        )
        self.sheet = self.participant.character_sheet

    def test_returns_round_context_instance(self) -> None:
        from actions.round_context import RoundContext, get_active_round_context

        result = get_active_round_context(self.sheet)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, RoundContext)

    def test_is_declaration_open_true_when_declaring(self) -> None:
        from actions.round_context import get_active_round_context

        result = get_active_round_context(self.sheet)
        assert result is not None
        self.assertTrue(result.is_declaration_open)

    def test_round_id_matches_encounter(self) -> None:
        from actions.round_context import get_active_round_context

        result = get_active_round_context(self.sheet)
        assert result is not None
        self.assertEqual(result.round_id, (self.encounter.pk, self.encounter.round_number))


class TestGetActiveRoundContextNotDeclaring(django.test.TestCase):
    """Character ACTIVE in a non-DECLARING encounter → is_declaration_open=False."""

    def test_is_declaration_open_false_when_resolving(self) -> None:
        encounter = CombatEncounterFactory(
            status=EncounterStatus.RESOLVING,
            round_number=2,
        )
        participant = CombatParticipantFactory(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
        )
        sheet = participant.character_sheet

        from actions.round_context import get_active_round_context

        result = get_active_round_context(sheet)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertFalse(result.is_declaration_open)

    def test_is_declaration_open_false_when_between_rounds(self) -> None:
        encounter = CombatEncounterFactory(
            status=EncounterStatus.BETWEEN_ROUNDS,
            round_number=3,
        )
        participant = CombatParticipantFactory(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
        )
        sheet = participant.character_sheet

        from actions.round_context import get_active_round_context

        result = get_active_round_context(sheet)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertFalse(result.is_declaration_open)


class TestGetActiveRoundContextCompletedEncounter(django.test.TestCase):
    """Character in a COMPLETED encounter → returns None (encounter is over)."""

    def test_completed_encounter_returns_none(self) -> None:
        encounter = CombatEncounterFactory(status=EncounterStatus.COMPLETED)
        CombatParticipantFactory(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
        )
        sheet = (
            encounter.participants.filter(status=ParticipantStatus.ACTIVE).first().character_sheet
        )

        from actions.round_context import get_active_round_context

        result = get_active_round_context(sheet)
        self.assertIsNone(result)


class TestGetActiveRoundContextInactiveParticipant(django.test.TestCase):
    """Character with FLED/REMOVED participant status → returns None."""

    def test_fled_participant_returns_none(self) -> None:
        encounter = CombatEncounterFactory(status=EncounterStatus.DECLARING)
        participant = CombatParticipantFactory(
            encounter=encounter,
            status=ParticipantStatus.FLED,
        )
        sheet = participant.character_sheet

        from actions.round_context import get_active_round_context

        result = get_active_round_context(sheet)
        self.assertIsNone(result)

    def test_removed_participant_returns_none(self) -> None:
        encounter = CombatEncounterFactory(status=EncounterStatus.DECLARING)
        participant = CombatParticipantFactory(
            encounter=encounter,
            status=ParticipantStatus.REMOVED,
        )
        sheet = participant.character_sheet

        from actions.round_context import get_active_round_context

        result = get_active_round_context(sheet)
        self.assertIsNone(result)


class TestRoundContextRecordDeclarationStub(django.test.TestCase):
    """record_declaration raises NotImplementedError (stub until next task)."""

    def test_record_declaration_raises_not_implemented(self) -> None:
        encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        participant = CombatParticipantFactory(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
        )
        sheet = participant.character_sheet

        from actions.round_context import get_active_round_context

        result = get_active_round_context(sheet)
        assert result is not None
        with self.assertRaises(NotImplementedError):
            result.record_declaration(sheet, object(), {})
