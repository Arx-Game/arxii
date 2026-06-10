"""Tests for encounter risk acknowledgement (#777).

acknowledge_encounter_risk is idempotent; voluntary entry points (self-join,
hostile-cast initiation) record acknowledgements; GM add_participant does not;
encounter_requiring_risk_acknowledgement implements the gate truth table.
"""

from evennia.utils.test_resources import EvenniaTestCase


class _RiskAckTestBase(EvenniaTestCase):
    @staticmethod
    def _make_sheet():
        from world.character_sheets.factories import CharacterSheetFactory
        from world.vitals.models import CharacterVitals

        sheet = CharacterSheetFactory()
        CharacterVitals.objects.create(
            character_sheet=sheet, health=50, max_health=50, base_max_health=50
        )
        return sheet

    @staticmethod
    def _make_scene_with_room():
        from evennia import create_object

        from world.scenes.factories import SceneFactory

        room = create_object("typeclasses.rooms.Room", key="Risk Room", nohome=True)
        scene = SceneFactory(location=room)
        return scene, room

    @staticmethod
    def _make_encounter(scene, room, risk_level):
        from world.combat.constants import EncounterStatus, EncounterType
        from world.combat.models import CombatEncounter

        return CombatEncounter.objects.create(
            room=room,
            scene=scene,
            status=EncounterStatus.BETWEEN_ROUNDS,
            risk_level=risk_level,
            encounter_type=EncounterType.PARTY_COMBAT,
        )


class AcknowledgeEncounterRiskTests(_RiskAckTestBase):
    def test_acknowledge_is_idempotent_and_snapshots_level(self):
        from world.combat.constants import RiskLevel
        from world.combat.models import EncounterRiskAcknowledgement
        from world.combat.services import acknowledge_encounter_risk

        sheet = self._make_sheet()
        scene, room = self._make_scene_with_room()
        encounter = self._make_encounter(scene, room, RiskLevel.LETHAL)

        first = acknowledge_encounter_risk(encounter, sheet)
        second = acknowledge_encounter_risk(encounter, sheet)

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.acknowledged_risk_level, RiskLevel.LETHAL)
        self.assertEqual(EncounterRiskAcknowledgement.objects.count(), 1)

    def test_join_encounter_records_acknowledgement(self):
        from world.combat.constants import RiskLevel
        from world.combat.models import EncounterRiskAcknowledgement
        from world.combat.services import join_encounter

        sheet = self._make_sheet()
        scene, room = self._make_scene_with_room()
        encounter = self._make_encounter(scene, room, RiskLevel.EXTREME)

        join_encounter(encounter, sheet)

        ack = EncounterRiskAcknowledgement.objects.get(encounter=encounter, character_sheet=sheet)
        self.assertEqual(ack.acknowledged_risk_level, RiskLevel.EXTREME)

    def test_gm_add_participant_does_not_record(self):
        from world.combat.constants import RiskLevel
        from world.combat.models import EncounterRiskAcknowledgement
        from world.combat.services import add_participant

        sheet = self._make_sheet()
        scene, room = self._make_scene_with_room()
        encounter = self._make_encounter(scene, room, RiskLevel.LETHAL)

        add_participant(encounter, sheet)

        self.assertFalse(EncounterRiskAcknowledgement.objects.exists())

    def test_cast_seed_records_caster_acknowledgement(self):
        from world.combat.cast_seed import seed_or_feed_encounter_from_cast
        from world.combat.models import EncounterRiskAcknowledgement
        from world.magic.factories import TechniqueFactory

        caster = self._make_sheet()
        target = self._make_sheet()
        scene, room = self._make_scene_with_room()

        encounter = seed_or_feed_encounter_from_cast(
            caster_sheet=caster,
            target_sheet=target,
            technique=TechniqueFactory(),
            scene=scene,
            room=room,
        )

        self.assertTrue(
            EncounterRiskAcknowledgement.objects.filter(
                encounter=encounter, character_sheet=caster
            ).exists()
        )
        # The dragged-in target never acknowledged.
        self.assertFalse(
            EncounterRiskAcknowledgement.objects.filter(
                encounter=encounter, character_sheet=target
            ).exists()
        )


class GateQueryTests(_RiskAckTestBase):
    def _gate(self, scene, sheet):
        from world.combat.cast_seed import encounter_requiring_risk_acknowledgement

        return encounter_requiring_risk_acknowledgement(scene, sheet)

    def test_no_feedable_encounter_returns_none(self):
        sheet = self._make_sheet()
        scene, _room = self._make_scene_with_room()
        self.assertIsNone(self._gate(scene, sheet))

    def test_moderate_encounter_returns_none(self):
        from world.combat.constants import RiskLevel

        sheet = self._make_sheet()
        scene, room = self._make_scene_with_room()
        self._make_encounter(scene, room, RiskLevel.MODERATE)
        self.assertIsNone(self._gate(scene, sheet))

    def test_high_encounter_returns_none(self):
        # The boundary is EXTREME+: HIGH does not gate.
        from world.combat.constants import RiskLevel

        sheet = self._make_sheet()
        scene, room = self._make_scene_with_room()
        self._make_encounter(scene, room, RiskLevel.HIGH)
        self.assertIsNone(self._gate(scene, sheet))

    def test_lethal_encounter_gates_unacknowledged_outsider(self):
        from world.combat.constants import RiskLevel

        sheet = self._make_sheet()
        scene, room = self._make_scene_with_room()
        encounter = self._make_encounter(scene, room, RiskLevel.LETHAL)
        self.assertEqual(self._gate(scene, sheet), encounter)

    def test_acknowledged_character_not_gated(self):
        from world.combat.constants import RiskLevel
        from world.combat.services import acknowledge_encounter_risk

        sheet = self._make_sheet()
        scene, room = self._make_scene_with_room()
        encounter = self._make_encounter(scene, room, RiskLevel.LETHAL)
        acknowledge_encounter_risk(encounter, sheet)
        self.assertIsNone(self._gate(scene, sheet))

    def test_active_participant_not_gated(self):
        from world.combat.constants import RiskLevel
        from world.combat.models import EncounterRiskAcknowledgement
        from world.combat.services import add_participant

        sheet = self._make_sheet()
        scene, room = self._make_scene_with_room()
        encounter = self._make_encounter(scene, room, RiskLevel.EXTREME)
        # GM placement: ACTIVE participant with no ack row — the participant
        # check alone must suppress the gate.
        add_participant(encounter, sheet)
        self.assertFalse(EncounterRiskAcknowledgement.objects.exists())
        self.assertIsNone(self._gate(scene, sheet))

    def test_active_opponent_not_gated(self):
        from world.combat.constants import OpponentTier, RiskLevel
        from world.combat.services import add_opponent

        sheet = self._make_sheet()
        scene, room = self._make_scene_with_room()
        encounter = self._make_encounter(scene, room, RiskLevel.LETHAL)
        add_opponent(
            encounter,
            name=sheet.character.key,
            tier=OpponentTier.ELITE,
            max_health=50,
            threat_pool=None,
            existing_objectdb=sheet.character,
        )
        self.assertIsNone(self._gate(scene, sheet))
