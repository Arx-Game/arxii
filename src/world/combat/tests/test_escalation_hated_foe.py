"""Tests for the hated-foe escalation spike leg (#2013, decisions 5-6)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import CombatAllegiance, ParticipantStatus, SurgeTriggerKind
from world.combat.escalation import check_hated_foe_surges_for_new_opponent
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    EscalationCurveFactory,
)
from world.combat.models import DramaticSurgeRecord
from world.combat.services import add_opponent, join_encounter
from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement
from world.mechanics.services import begin_engagement
from world.relationships.constants import TrackSign
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipTrackFactory,
    RelationshipTrackProgressFactory,
)
from world.relationships.models import CharacterRelationship
from world.scenes.factories import PersonaFactory


class HatedFoeSpikeTests(TestCase):
    def setUp(self):
        self.curve = EscalationCurveFactory(hated_foe_spike_intensity_amount=6)
        self.encounter = CombatEncounterFactory(escalation_curve=self.curve)
        self.pc = CombatParticipantFactory(
            encounter=self.encounter, status=ParticipantStatus.ACTIVE
        )
        self.pc_char = self.pc.character_sheet.character
        begin_engagement(self.pc_char, EngagementType.COMBAT, source=self.encounter)
        self.foe_sheet = CharacterSheetFactory()
        self.foe_persona = PersonaFactory(character_sheet=self.foe_sheet)

    def _hate(self, *, points=0, sign=TrackSign.NEGATIVE, fuels=True):
        track = RelationshipTrackFactory(sign=sign, fuels_escalation_spikes=fuels)
        relationship = CharacterRelationshipFactory(
            source=self.pc.character_sheet,
            target=self.foe_sheet,
            is_active=True,
            is_pending=False,
        )
        RelationshipTrackProgressFactory(
            relationship=relationship, track=track, developed_points=points, capacity=max(points, 1)
        )

    def _intensity(self) -> int:
        return CharacterEngagement.objects.get(character=self.pc_char).intensity_modifier

    def test_surge_on_opponent_add_when_hated(self):
        self._hate()

        opponent = add_opponent(
            self.encounter,
            name=self.foe_sheet.character.key,
            tier="mook",
            threat_pool=None,
            max_health=10,
            persona=self.foe_persona,
        )

        self.assertEqual(self._intensity(), self.curve.hated_foe_spike_intensity_amount)
        self.assertEqual(
            DramaticSurgeRecord.objects.filter(
                trigger_kind=SurgeTriggerKind.HATED_FOE,
                subject_sheet=self.foe_sheet,
            ).count(),
            1,
        )
        self.assertEqual(opponent.persona_id, self.foe_persona.pk)

    def test_no_minimum_track_points_gate(self):
        """Unlike peril/grief, hated-foe qualification has NO spike_minimum_track_points
        floor — sign + fuels_escalation_spikes alone qualify (spec decisions 4-6)."""
        self._hate(points=0)

        add_opponent(
            self.encounter,
            name="Foe",
            tier="mook",
            threat_pool=None,
            max_health=10,
            persona=self.foe_persona,
        )

        self.assertEqual(self._intensity(), self.curve.hated_foe_spike_intensity_amount)

    def test_no_surge_on_positive_sign_track(self):
        self._hate(sign=TrackSign.POSITIVE)

        add_opponent(
            self.encounter,
            name="Foe",
            tier="mook",
            threat_pool=None,
            max_health=10,
            persona=self.foe_persona,
        )

        self.assertEqual(self._intensity(), 0)

    def test_no_surge_without_persona(self):
        """A PC duel mirror (and every persona-less mook) never sets persona —
        _opponent_kwargs_from_sheet never passes it — so this guard alone
        enforces decision 6 (no PC-opponent surges)."""
        self._hate()

        add_opponent(
            self.encounter, name="Nameless Mook", tier="mook", threat_pool=None, max_health=10
        )

        self.assertEqual(self._intensity(), 0)

    def test_no_surge_for_ally_allegiance_opponent(self):
        self._hate()

        opponent = CombatOpponentFactory(
            encounter=self.encounter, persona=self.foe_persona, allegiance=CombatAllegiance.ALLY
        )
        check_hated_foe_surges_for_new_opponent(opponent)

        self.assertEqual(self._intensity(), 0)

    def test_no_surge_without_curve(self):
        plain_encounter = CombatEncounterFactory(escalation_curve=None)
        pc = CombatParticipantFactory(encounter=plain_encounter, status=ParticipantStatus.ACTIVE)
        begin_engagement(
            pc.character_sheet.character, EngagementType.COMBAT, source=plain_encounter
        )
        self._hate()
        CharacterRelationshipFactory(
            source=pc.character_sheet, target=self.foe_sheet, is_active=True, is_pending=False
        )

        opponent = CombatOpponentFactory(encounter=plain_encounter, persona=self.foe_persona)
        check_hated_foe_surges_for_new_opponent(opponent)

        self.assertEqual(DramaticSurgeRecord.objects.count(), 0)

    def test_deduped_on_repeat_check(self):
        self._hate()
        opponent = CombatOpponentFactory(encounter=self.encounter, persona=self.foe_persona)

        check_hated_foe_surges_for_new_opponent(opponent)
        check_hated_foe_surges_for_new_opponent(opponent)

        self.assertEqual(self._intensity(), self.curve.hated_foe_spike_intensity_amount)

    def test_surge_on_pc_join_when_foe_already_present(self):
        self._hate()
        CombatOpponentFactory(encounter=self.encounter, persona=self.foe_persona)
        latecomer_sheet = CharacterSheetFactory()
        CharacterRelationshipFactory(
            source=latecomer_sheet, target=self.foe_sheet, is_active=True, is_pending=False
        )
        track = RelationshipTrackFactory(sign=TrackSign.NEGATIVE, fuels_escalation_spikes=True)
        relationship = CharacterRelationship.objects.get(
            source=latecomer_sheet, target=self.foe_sheet
        )
        RelationshipTrackProgressFactory(
            relationship=relationship, track=track, developed_points=1, capacity=1
        )
        self.encounter.status = "declaring"
        self.encounter.save(update_fields=["status"])

        participant = join_encounter(self.encounter, latecomer_sheet)
        begin_engagement(latecomer_sheet.character, EngagementType.COMBAT, source=self.encounter)
        # join_encounter already ensured an engagement via _create_participant;
        # begin_engagement is idempotent here (re-source is a no-op if identical).
        del participant

        latecomer_intensity = CharacterEngagement.objects.get(
            character=latecomer_sheet.character
        ).intensity_modifier
        self.assertEqual(latecomer_intensity, self.curve.hated_foe_spike_intensity_amount)
