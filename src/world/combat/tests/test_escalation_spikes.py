"""Tests for relationship-event escalation intensity spikes (#872, Task 8).

End-to-end through emit_event: seeded TriggerDefinitions (wire_escalation_content)
+ room Trigger rows (install_escalation_room_triggers) + the flows dispatch
pipeline calling relationship_spike_handler via CALL_SERVICE_FUNCTION.
"""

from django.test import TestCase

from flows.constants import EventName
from flows.emit import emit_event
from flows.events.payloads import CharacterIncapacitatedPayload
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import ParticipantStatus
from world.combat.escalation import (
    apply_relationship_escalation_spike,
    install_escalation_room_triggers,
    relationship_spike_handler,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    EscalationCurveFactory,
    wire_escalation_content,
)
from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement
from world.mechanics.services import begin_engagement
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipTrackFactory,
    RelationshipTrackProgressFactory,
)


class EscalationSpikeTests(TestCase):
    """Bonded co-combatants spike intensity when a character falls."""

    def setUp(self):
        self.curve = EscalationCurveFactory(
            spike_intensity_amount=3,
            spike_minimum_track_points=10,
        )
        self.encounter = CombatEncounterFactory(escalation_curve=self.curve)
        self.participant_a = CombatParticipantFactory(
            encounter=self.encounter, status=ParticipantStatus.ACTIVE
        )
        self.participant_b = CombatParticipantFactory(
            encounter=self.encounter, status=ParticipantStatus.ACTIVE
        )
        self.sheet_a = self.participant_a.character_sheet
        self.sheet_b = self.participant_b.character_sheet
        self.char_a = self.sheet_a.character
        self.char_b = self.sheet_b.character
        # Real combat emits from room == character.location (services.py);
        # the handler walks payload.character.location back to the room.
        self.char_a.location = self.encounter.room
        self.char_b.location = self.encounter.room
        begin_engagement(self.char_a, EngagementType.COMBAT, source=self.encounter)
        begin_engagement(self.char_b, EngagementType.COMBAT, source=self.encounter)
        wire_escalation_content()
        install_escalation_room_triggers(self.encounter)

    def _bond(self, source_sheet, target_sheet, *, points=10, fuels=True):
        """Create an active, non-pending relationship with track progress."""
        track = RelationshipTrackFactory(fuels_escalation_spikes=fuels)
        relationship = CharacterRelationshipFactory(
            source=source_sheet,
            target=target_sheet,
            is_active=True,
            is_pending=False,
        )
        RelationshipTrackProgressFactory(
            relationship=relationship,
            track=track,
            developed_points=points,
            capacity=points,
        )
        return relationship

    def _emit_fall(self, character):
        emit_event(
            EventName.CHARACTER_INCAPACITATED,
            CharacterIncapacitatedPayload(character=character, source_event=None),
            location=self.encounter.room,
        )

    def _intensity(self, character) -> int:
        return CharacterEngagement.objects.get(character=character).intensity_modifier

    def test_spike_applies_to_bonded_survivor_via_emit(self):
        self._bond(self.sheet_a, self.sheet_b)

        self._emit_fall(self.char_b)

        self.assertEqual(self._intensity(self.char_a), self.curve.spike_intensity_amount)
        self.assertEqual(self._intensity(self.char_b), 0)

    def test_no_spike_for_unbonded_participant(self):
        self._bond(self.sheet_a, self.sheet_b)
        participant_c = CombatParticipantFactory(
            encounter=self.encounter, status=ParticipantStatus.ACTIVE
        )
        char_c = participant_c.character_sheet.character
        begin_engagement(char_c, EngagementType.COMBAT, source=self.encounter)

        self._emit_fall(self.char_b)

        self.assertEqual(self._intensity(self.char_a), self.curve.spike_intensity_amount)
        self.assertEqual(self._intensity(char_c), 0)

    def test_no_spike_below_track_points_gate(self):
        self._bond(self.sheet_a, self.sheet_b, points=9)

        self._emit_fall(self.char_b)

        self.assertEqual(self._intensity(self.char_a), 0)

    def test_no_spike_on_non_spike_track(self):
        self._bond(self.sheet_a, self.sheet_b, fuels=False)

        self._emit_fall(self.char_b)

        self.assertEqual(self._intensity(self.char_a), 0)

    def test_direct_service_noop_without_escalating_encounter(self):
        self._bond(self.sheet_a, self.sheet_b)
        plain_encounter = CombatEncounterFactory(escalation_curve=None)

        apply_relationship_escalation_spike(
            fallen_character=self.char_b,
            room=plain_encounter.room,
        )

        self.assertEqual(self._intensity(self.char_a), 0)

    def test_handler_noop_when_character_has_no_location(self):
        sheet = CharacterSheetFactory()
        character = sheet.character
        self.assertIsNone(character.location)

        relationship_spike_handler(
            payload=CharacterIncapacitatedPayload(character=character, source_event=None)
        )

        self.assertEqual(self._intensity(self.char_a), 0)
