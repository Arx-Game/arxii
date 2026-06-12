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
from world.combat.services import apply_damage_to_participant
from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement
from world.mechanics.services import begin_engagement
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipTrackFactory,
    RelationshipTrackProgressFactory,
)
from world.vitals.models import CharacterVitals


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

    def _reset_vitals(self, sheet, *, health=100, max_health=100):
        """Ensure the sheet has CharacterVitals at a known health level."""
        vitals, _ = CharacterVitals.objects.get_or_create(
            character_sheet=sheet,
            defaults={"health": health, "max_health": max_health},
        )
        vitals.health = health
        vitals.max_health = max_health
        vitals.save()
        return vitals

    def test_no_double_spike_on_repeat_hits_while_down(self):
        """Repeat hits inside the knockout band emit no further beats.

        The transition latch in apply_damage_to_participant fires
        CHARACTER_INCAPACITATED only when the hit moves the target INTO the
        knockout band — a second hit that keeps them there stays silent, so
        the bonded survivor spikes exactly once.
        """
        self._bond(self.sheet_a, self.sheet_b)
        self._reset_vitals(self.sheet_b)

        # 100 -> 15 (15% <= 20% band, above death): transition, emits.
        apply_damage_to_participant(self.participant_b, 85)
        # 15 -> 10: already in the band, no re-emit.
        apply_damage_to_participant(self.participant_b, 5)

        self.assertEqual(self._intensity(self.char_a), self.curve.spike_intensity_amount)

    def test_force_death_emits_single_beat(self):
        """A knockout-band hit with force_death emits only CHARACTER_KILLED.

        Death supersedes incapacitation: one narrative beat, one event — the
        bonded survivor spikes once (via the killed event), not twice.
        """
        self._bond(self.sheet_a, self.sheet_b)
        self._reset_vitals(self.sheet_b)

        # 100 -> 15 is knockout-band-eligible, but force_death fires the
        # death gate instead; the incapacitated emit is skipped.
        apply_damage_to_participant(self.participant_b, 85, force_death=True)

        self.assertEqual(self._intensity(self.char_a), self.curve.spike_intensity_amount)

    def test_no_double_dip_across_co_located_encounters(self):
        """A survivor in two co-located escalating encounters spikes once.

        The engagement-source guard ties the spike to the encounter the
        survivor's COMBAT engagement is sourced to (encounter 1); the second
        encounter's participant row does not double-dip.
        """
        self._bond(self.sheet_a, self.sheet_b)
        other_curve = EscalationCurveFactory(
            spike_intensity_amount=7,
            spike_minimum_track_points=10,
        )
        other_encounter = CombatEncounterFactory(
            room=self.encounter.room,
            escalation_curve=other_curve,
        )
        CombatParticipantFactory(
            encounter=other_encounter,
            character_sheet=self.sheet_a,
            status=ParticipantStatus.ACTIVE,
        )
        install_escalation_room_triggers(other_encounter)

        self._emit_fall(self.char_b)

        # Encounter 1's curve amount exactly once — not 3+7 (both encounters)
        # and not 7 (the wrong encounter's curve).
        self.assertEqual(self._intensity(self.char_a), self.curve.spike_intensity_amount)

    def test_handler_noop_when_character_has_no_location(self):
        sheet = CharacterSheetFactory()
        character = sheet.character
        self.assertIsNone(character.location)

        relationship_spike_handler(
            payload=CharacterIncapacitatedPayload(character=character, source_event=None)
        )

        self.assertEqual(self._intensity(self.char_a), 0)
