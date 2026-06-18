"""Tests for create_pvp_duel (Task 5) and create_lethal_duel (Task 6)."""

from django.test import TestCase
from evennia import create_object

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import EncounterType, OpponentTier, RiskLevel
from world.combat.duels import create_lethal_duel, create_pvp_duel
from world.combat.factories import ThreatPoolFactory


class CreatePvpDuelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = CharacterSheetFactory()
        cls.b = CharacterSheetFactory()

    def setUp(self):
        # Create a fresh Room per test (ObjectDB is not deepcopy-safe).
        self.room = create_object("typeclasses.rooms.Room", key="Duel Room", nohome=True)

    def test_creates_two_participants_and_two_mirrors_non_lethal(self):
        enc = create_pvp_duel(self.a, self.b, self.room)
        self.assertEqual(enc.encounter_type, EncounterType.DUEL)
        self.assertFalse(enc.is_lethal)
        self.assertEqual(enc.participants.count(), 2)
        mirrors = enc.opponents.filter(mirrors_participant__isnull=False)
        self.assertEqual(mirrors.count(), 2)
        # Both duelists acknowledged the encounter risk.
        self.assertEqual(enc.risk_acknowledgements.count(), 2)

    def test_mirror_wiring_mirror_a_mirrors_participant_a(self):
        """mirror_A.mirrors_participant == participant whose sheet is challenger (A)."""
        enc = create_pvp_duel(self.a, self.b, self.room)
        participant_a = enc.participants.get(character_sheet=self.a)
        participant_b = enc.participants.get(character_sheet=self.b)
        mirror_a = enc.opponents.get(mirrors_participant=participant_a)
        mirror_b = enc.opponents.get(mirrors_participant=participant_b)
        # mirror_A uses A's objectdb (it IS A's body surface).
        self.assertEqual(mirror_a.objectdb_id, self.a.character_id)
        # mirror_B uses B's objectdb (it IS B's body surface).
        self.assertEqual(mirror_b.objectdb_id, self.b.character_id)

    def test_mirrors_have_no_threat_pool(self):
        enc = create_pvp_duel(self.a, self.b, self.room)
        mirrors = enc.opponents.filter(mirrors_participant__isnull=False)
        for mirror in mirrors:
            self.assertIsNone(mirror.threat_pool_id)

    def test_lethal_risk_raises_value_error(self):
        with self.assertRaises(ValueError):
            create_pvp_duel(self.a, self.b, self.room, risk_level=RiskLevel.LETHAL)

    def test_default_risk_level_is_moderate(self):
        enc = create_pvp_duel(self.a, self.b, self.room)
        self.assertEqual(enc.risk_level, RiskLevel.MODERATE)


class CreateLethalDuelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.pc_sheet = CharacterSheetFactory()
        # ThreatPool for the NPC opponent (deepcopy-safe — pure DB rows, no Evennia OD).
        cls.threat_pool = ThreatPoolFactory()

    def setUp(self):
        # Room must be created per test — ObjectDB is not deepcopy-safe.
        self.room = create_object("typeclasses.rooms.Room", key="Lethal Duel Room", nohome=True)
        self.opponent_kwargs = {
            "name": "Dueling Master",
            "max_health": 200,
            "threat_pool": self.threat_pool,
            "soak_value": 50,
        }

    def test_creates_duel_encounter_that_is_lethal(self):
        enc = create_lethal_duel(self.pc_sheet, self.opponent_kwargs, self.room)
        self.assertEqual(enc.encounter_type, EncounterType.DUEL)
        self.assertTrue(enc.is_lethal)
        self.assertEqual(enc.risk_level, RiskLevel.LETHAL)

    def test_creates_exactly_one_participant(self):
        enc = create_lethal_duel(self.pc_sheet, self.opponent_kwargs, self.room)
        self.assertEqual(enc.participants.count(), 1)
        self.assertEqual(enc.participants.get().character_sheet_id, self.pc_sheet.pk)

    def test_creates_exactly_one_non_mirror_opponent_with_tier(self):
        enc = create_lethal_duel(
            self.pc_sheet, self.opponent_kwargs, self.room, tier=OpponentTier.ELITE
        )
        self.assertEqual(enc.opponents.count(), 1)
        opp = enc.opponents.get()
        self.assertIsNone(opp.mirrors_participant_id)
        self.assertEqual(opp.tier, OpponentTier.ELITE)

    def test_opponent_has_threat_pool(self):
        enc = create_lethal_duel(self.pc_sheet, self.opponent_kwargs, self.room)
        opp = enc.opponents.get()
        self.assertEqual(opp.threat_pool_id, self.threat_pool.pk)

    def test_tier_overrides_opponent_kwargs_tier(self):
        """Explicit tier= param wins even if opponent_kwargs carries a different tier."""
        enc = create_lethal_duel(
            self.pc_sheet, self.opponent_kwargs, self.room, tier=OpponentTier.BOSS
        )
        opp = enc.opponents.get()
        self.assertEqual(opp.tier, OpponentTier.BOSS)

    def test_pc_is_not_auto_acknowledged(self):
        """PC must acknowledge via #777 gate — create_lethal_duel does NOT call
        acknowledge_encounter_risk for the PC."""
        enc = create_lethal_duel(self.pc_sheet, self.opponent_kwargs, self.room)
        self.assertEqual(enc.risk_acknowledgements.count(), 0)

    def test_encounter_gated_until_pc_acknowledges(self):
        """The lethal encounter has no acknowledgement record for the PC after
        creation; calling acknowledge_encounter_risk creates one (#777 gate).

        encounter_requiring_risk_acknowledgement uses the scene-scoped feedable-
        encounter check.  A third-party character (not yet a participant/opponent)
        is gated until they acknowledge; confirming the encounter is in
        RISK_LEVELS_REQUIRING_ACKNOWLEDGEMENT is sufficient for a participant
        whose acknowledgement is checked by the wider action layer.
        """
        from world.combat.cast_seed import encounter_requiring_risk_acknowledgement
        from world.combat.constants import RISK_LEVELS_REQUIRING_ACKNOWLEDGEMENT
        from world.combat.models import EncounterRiskAcknowledgement
        from world.combat.services import acknowledge_encounter_risk
        from world.scenes.factories import SceneFactory

        enc = create_lethal_duel(self.pc_sheet, self.opponent_kwargs, self.room)

        # No ack row for the PC — create_lethal_duel does not auto-acknowledge.
        self.assertFalse(
            EncounterRiskAcknowledgement.objects.filter(
                encounter=enc, character_sheet=self.pc_sheet
            ).exists()
        )

        # The encounter's risk level requires acknowledgement (#777).
        self.assertIn(enc.risk_level, RISK_LEVELS_REQUIRING_ACKNOWLEDGEMENT)

        # A bystander (not yet participant/opponent) is gated by
        # encounter_requiring_risk_acknowledgement as long as the encounter is
        # in a feedable status and they haven't acknowledged.
        bystander = CharacterSheetFactory()
        scene = SceneFactory(location=self.room)
        enc.scene = scene
        enc.save(update_fields=["scene"])
        self.assertEqual(encounter_requiring_risk_acknowledgement(scene, bystander), enc)

        # Once the bystander acknowledges the gate lifts.
        acknowledge_encounter_risk(enc, bystander)
        self.assertIsNone(encounter_requiring_risk_acknowledgement(scene, bystander))

        # After the PC explicitly acknowledges, the ack row exists.
        acknowledge_encounter_risk(enc, self.pc_sheet)
        self.assertTrue(
            EncounterRiskAcknowledgement.objects.filter(
                encounter=enc, character_sheet=self.pc_sheet
            ).exists()
        )

    def test_mook_tier_raises_value_error(self):
        with self.assertRaises(ValueError, msg="significant NPC only"):
            create_lethal_duel(
                self.pc_sheet, self.opponent_kwargs, self.room, tier=OpponentTier.MOOK
            )

    def test_swarm_tier_raises_value_error(self):
        with self.assertRaises(ValueError):
            create_lethal_duel(
                self.pc_sheet, self.opponent_kwargs, self.room, tier=OpponentTier.SWARM
            )

    def test_default_tier_is_elite(self):
        enc = create_lethal_duel(self.pc_sheet, self.opponent_kwargs, self.room)
        opp = enc.opponents.get()
        self.assertEqual(opp.tier, OpponentTier.ELITE)

    def test_hero_killer_tier_is_valid(self):
        enc = create_lethal_duel(
            self.pc_sheet, self.opponent_kwargs, self.room, tier=OpponentTier.HERO_KILLER
        )
        opp = enc.opponents.get()
        self.assertEqual(opp.tier, OpponentTier.HERO_KILLER)
