"""Tests for the mortal-peril escalation spike leg (#2013).

End-to-end through emit_event, mirroring test_escalation_spikes.py's shape
for the existing grief spike.
"""

from django.test import TestCase, tag

from world.combat.constants import ParticipantStatus, SurgeTriggerKind
from world.combat.escalation import install_escalation_room_triggers
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    EscalationCurveFactory,
    wire_escalation_content,
)
from world.combat.models import DramaticSurgeRecord
from world.conditions.factories import BleedingOutConditionFactory, ConditionStageFactory
from world.conditions.services import apply_condition
from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement
from world.mechanics.services import begin_engagement
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipTrackFactory,
    RelationshipTrackProgressFactory,
)


@tag("postgres")
class EscalationPerilSpikeTests(TestCase):
    """Bonded co-combatants spike intensity when an ally enters mortal peril.

    Bleeding Out is progressive — apply_condition uses PG DISTINCT ON — so
    this class requires Postgres (see test_resolution.py's precedent).
    """

    def setUp(self):
        self.curve = EscalationCurveFactory(
            peril_spike_intensity_amount=5,
            spike_minimum_track_points=10,
        )
        self.encounter = CombatEncounterFactory(escalation_curve=self.curve)
        self.protector = CombatParticipantFactory(
            encounter=self.encounter, status=ParticipantStatus.ACTIVE
        )
        self.victim = CombatParticipantFactory(
            encounter=self.encounter, status=ParticipantStatus.ACTIVE
        )
        self.protector_char = self.protector.character_sheet.character
        self.victim_char = self.victim.character_sheet.character
        self.protector_char.location = self.encounter.room
        self.victim_char.location = self.encounter.room
        begin_engagement(self.protector_char, EngagementType.COMBAT, source=self.encounter)
        begin_engagement(self.victim_char, EngagementType.COMBAT, source=self.encounter)
        wire_escalation_content()
        install_escalation_room_triggers(self.encounter)
        self.bleed_out = BleedingOutConditionFactory()
        ConditionStageFactory(
            condition=self.bleed_out, stage_order=1, name="Bleeding", rounds_to_next=None
        )

    def _bond(self, *, points=10, fuels=True):
        track = RelationshipTrackFactory(fuels_escalation_spikes=fuels)
        relationship = CharacterRelationshipFactory(
            source=self.protector.character_sheet,
            target=self.victim.character_sheet,
            is_active=True,
            is_pending=False,
        )
        RelationshipTrackProgressFactory(
            relationship=relationship, track=track, developed_points=points, capacity=points
        )

    def _apply_bleed_out(self):
        apply_condition(target=self.victim_char, condition=self.bleed_out)

    def _intensity(self, character) -> int:
        return CharacterEngagement.objects.get(character=character).intensity_modifier

    def test_spike_on_ally_entering_mortal_peril(self):
        self._bond()

        self._apply_bleed_out()

        self.assertEqual(
            self._intensity(self.protector_char), self.curve.peril_spike_intensity_amount
        )
        self.assertEqual(
            DramaticSurgeRecord.objects.filter(trigger_kind=SurgeTriggerKind.ALLY_PERIL).count(), 1
        )

    def test_no_spike_below_track_points_gate(self):
        self._bond(points=9)

        self._apply_bleed_out()

        self.assertEqual(self._intensity(self.protector_char), 0)

    def test_unrelated_condition_does_not_spike(self):
        """A non-acute-peril CONDITION_APPLIED (e.g. any other stub condition)
        is filtered out in Python before any relationship read happens."""
        self._bond()
        from world.conditions.factories import ConditionTemplateFactory

        other = ConditionTemplateFactory(name="Minor Bruise")
        apply_condition(target=self.victim_char, condition=other)

        self.assertEqual(self._intensity(self.protector_char), 0)

    def test_fires_once_per_victim_per_encounter(self):
        """A re-applied Bleeding Out (stacked severity) surges only once."""
        self._bond()

        self._apply_bleed_out()
        self._apply_bleed_out()

        self.assertEqual(
            self._intensity(self.protector_char), self.curve.peril_spike_intensity_amount
        )
        self.assertEqual(
            DramaticSurgeRecord.objects.filter(trigger_kind=SurgeTriggerKind.ALLY_PERIL).count(), 1
        )
