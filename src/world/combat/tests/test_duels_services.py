"""Tests for create_pvp_duel (Task 5 — symmetric mirror setup)."""

from django.test import TestCase
from evennia import create_object

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import EncounterType, RiskLevel
from world.combat.duels import create_pvp_duel


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
