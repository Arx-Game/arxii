"""A bonded companion falling surges its owner (#3575).

End to end: apply_damage_to_opponent defeats the companion's ALLY CombatOpponent,
emits CHARACTER_INCAPACITATED, the seeded escalation_spike_on_incapacitated trigger
dispatches relationship_spike_handler, and the owner's engagement surges once.
"""

from django.test import TestCase, override_settings
from django.utils import timezone
from evennia.utils.create import create_object

from typeclasses.companions import CompanionObject
from world.combat.constants import OpponentStatus, ParticipantStatus, SurgeTriggerKind
from world.combat.escalation import install_escalation_room_triggers
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    EscalationCurveFactory,
    ThreatPoolFactory,
    wire_escalation_content,
)
from world.combat.models import DramaticSurgeRecord
from world.combat.services import apply_damage_to_opponent
from world.companions.factories import CompanionArchetypeFactory, CompanionFactory
from world.companions.services import materialize_companion_as_combat_opponent
from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement
from world.mechanics.services import begin_engagement
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipTrackFactory,
    RelationshipTrackProgressFactory,
)


@override_settings(SEED_SAMPLE_CONTENT=True)
class CompanionFallSurgeTests(TestCase):
    def setUp(self):
        self.curve = EscalationCurveFactory(
            spike_intensity_amount=3,
            spike_minimum_track_points=10,
        )
        self.encounter = CombatEncounterFactory(escalation_curve=self.curve)
        self.owner_participant = CombatParticipantFactory(
            encounter=self.encounter, status=ParticipantStatus.ACTIVE
        )
        self.owner_sheet = self.owner_participant.character_sheet
        self.owner = self.owner_sheet.character
        self.owner.location = self.encounter.room
        begin_engagement(self.owner, EngagementType.COMBAT, source=self.encounter)

        archetype = CompanionArchetypeFactory(name="SurgeBeast", max_health=20, soak_value=0)
        self.companion = CompanionFactory(owner=self.owner_sheet, archetype=archetype, name="Ash")
        # relationship_spike_handler walks payload.character.location back to the room,
        # so the companion's live object must stand in the encounter room.
        obj = create_object(CompanionObject, key="Ash", location=self.encounter.room, nohome=True)
        self.companion.objectdb = obj
        self.companion.save(update_fields=["objectdb"])
        self.opponent = materialize_companion_as_combat_opponent(
            self.companion, self.encounter, threat_pool=ThreatPoolFactory()
        )
        wire_escalation_content()
        install_escalation_room_triggers(self.encounter)

    def _bond(self, source_sheet, *, points=10, fuels=True):
        track = RelationshipTrackFactory(fuels_escalation_spikes=fuels)
        relationship = CharacterRelationshipFactory(
            source=source_sheet,
            target=None,
            target_companion=self.companion,
            is_active=True,
            is_pending=False,
        )
        RelationshipTrackProgressFactory(
            relationship=relationship, track=track, developed_points=points, capacity=points
        )
        return relationship

    def _intensity(self, sheet) -> int:
        return CharacterEngagement.objects.get(character=sheet).intensity_modifier

    def _fell(self):
        apply_damage_to_opponent(self.opponent, 100)
        self.opponent.refresh_from_db()
        self.assertEqual(self.opponent.status, OpponentStatus.DEFEATED)

    def _records(self):
        return DramaticSurgeRecord.objects.filter(
            trigger_kind=SurgeTriggerKind.ALLY_FALLEN, subject_companion=self.companion
        )

    def test_bonded_owner_surges_once_when_companion_falls(self):
        self._bond(self.owner_sheet)
        self._fell()
        self.assertEqual(self._intensity(self.owner_sheet), 3)
        self.assertEqual(self._records().count(), 1)
        record = self._records().get()
        self.assertEqual(record.participant, self.owner_participant)
        self.assertIsNone(record.subject_sheet)

    def test_repeat_damage_on_the_fallen_companion_does_not_surge_again(self):
        self._bond(self.owner_sheet)
        self._fell()
        apply_damage_to_opponent(self.opponent, 100)
        self.assertEqual(self._intensity(self.owner_sheet), 3)
        self.assertEqual(self._records().count(), 1)

    def test_no_relationship_no_surge(self):
        self._fell()
        self.assertEqual(self._intensity(self.owner_sheet), 0)
        self.assertFalse(self._records().exists())

    def test_below_track_floor_no_surge(self):
        self._bond(self.owner_sheet, points=5)
        self._fell()
        self.assertEqual(self._intensity(self.owner_sheet), 0)

    def test_non_spike_track_no_surge(self):
        self._bond(self.owner_sheet, fuels=False)
        self._fell()
        self.assertEqual(self._intensity(self.owner_sheet), 0)

    def test_other_participant_without_bond_does_not_surge(self):
        self._bond(self.owner_sheet)
        other = CombatParticipantFactory(encounter=self.encounter, status=ParticipantStatus.ACTIVE)
        other.character_sheet.character.location = self.encounter.room
        begin_engagement(
            other.character_sheet.character, EngagementType.COMBAT, source=self.encounter
        )
        self._fell()
        self.assertEqual(self._intensity(self.owner_sheet), 3)
        self.assertEqual(self._intensity(other.character_sheet), 0)

    def test_released_companion_emits_nothing(self):
        self._bond(self.owner_sheet)
        self.companion.released_at = timezone.now()
        self.companion.save(update_fields=["released_at"])
        self._fell()
        self.assertEqual(self._intensity(self.owner_sheet), 0)
        self.assertFalse(self._records().exists())

    def test_curveless_encounter_is_a_no_op(self):
        self._bond(self.owner_sheet)
        self.encounter.escalation_curve = None
        self.encounter.save(update_fields=["escalation_curve"])
        self._fell()
        self.assertEqual(self._intensity(self.owner_sheet), 0)
