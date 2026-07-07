"""Tests for the shared apply_dramatic_surge primitive (#2013)."""

from django.test import TestCase

from world.combat.constants import ParticipantStatus, SurgeTriggerKind
from world.combat.escalation import apply_dramatic_surge
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    EscalationCurveFactory,
)
from world.combat.models import DramaticSurgeRecord
from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement
from world.mechanics.services import begin_engagement


class ApplyDramaticSurgeTests(TestCase):
    def setUp(self):
        self.curve = EscalationCurveFactory(surge_narration="{character}'s power surges.")
        self.encounter = CombatEncounterFactory(escalation_curve=self.curve)
        self.participant = CombatParticipantFactory(
            encounter=self.encounter, status=ParticipantStatus.ACTIVE
        )
        self.character = self.participant.character_sheet.character
        begin_engagement(self.character, EngagementType.COMBAT, source=self.encounter)

    def _intensity(self) -> int:
        return CharacterEngagement.objects.get(character=self.character).intensity_modifier

    def test_writes_engagement_and_records_and_returns_beat(self):
        beat = apply_dramatic_surge(
            encounter=self.encounter,
            participant=self.participant,
            amount=4,
            trigger_kind=SurgeTriggerKind.HIGH_STAKES,
        )
        self.assertEqual(self._intensity(), 4)
        self.assertEqual(DramaticSurgeRecord.objects.count(), 1)
        self.assertIsNotNone(beat)
        self.assertEqual(beat.amount, 4)
        self.assertEqual(beat.trigger_kind, SurgeTriggerKind.HIGH_STAKES)
        self.assertEqual(beat.narration, f"{self.character.db_key}'s power surges.")

    def test_second_identical_call_is_a_no_op(self):
        apply_dramatic_surge(
            encounter=self.encounter,
            participant=self.participant,
            amount=4,
            trigger_kind=SurgeTriggerKind.HIGH_STAKES,
        )
        beat = apply_dramatic_surge(
            encounter=self.encounter,
            participant=self.participant,
            amount=4,
            trigger_kind=SurgeTriggerKind.HIGH_STAKES,
        )
        self.assertIsNone(beat)
        self.assertEqual(self._intensity(), 4)
        self.assertEqual(DramaticSurgeRecord.objects.count(), 1)

    def test_no_engagement_is_a_clean_noop(self):
        other_participant = CombatParticipantFactory(
            encounter=self.encounter, status=ParticipantStatus.ACTIVE
        )
        beat = apply_dramatic_surge(
            encounter=self.encounter,
            participant=other_participant,
            amount=4,
            trigger_kind=SurgeTriggerKind.HIGH_STAKES,
        )
        self.assertIsNone(beat)
        self.assertEqual(DramaticSurgeRecord.objects.count(), 0)

    def test_blank_curve_narration_uses_default_line(self):
        plain_curve = EscalationCurveFactory()
        encounter = CombatEncounterFactory(escalation_curve=plain_curve)
        participant = CombatParticipantFactory(encounter=encounter, status=ParticipantStatus.ACTIVE)
        character = participant.character_sheet.character
        begin_engagement(character, EngagementType.COMBAT, source=encounter)

        beat = apply_dramatic_surge(
            encounter=encounter,
            participant=participant,
            amount=2,
            trigger_kind=SurgeTriggerKind.HIGH_STAKES,
        )

        self.assertIn(character.db_key, beat.narration)

    def test_narration_template_never_leaks_other_placeholders(self):
        """Leak guard: only literal '{character}' substitutes; any other
        brace-token in an authored template stays inert literal text — never
        raises, never resolves to a real value."""
        leaky_curve = EscalationCurveFactory(
            surge_narration="{character} reacts to {subject}'s peril."
        )
        encounter = CombatEncounterFactory(escalation_curve=leaky_curve)
        participant = CombatParticipantFactory(encounter=encounter, status=ParticipantStatus.ACTIVE)
        character = participant.character_sheet.character
        begin_engagement(character, EngagementType.COMBAT, source=encounter)

        beat = apply_dramatic_surge(
            encounter=encounter,
            participant=participant,
            amount=2,
            trigger_kind=SurgeTriggerKind.ALLY_PERIL,
        )

        self.assertEqual(beat.narration, f"{character.db_key} reacts to {{subject}}'s peril.")
