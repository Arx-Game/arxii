"""Pending wind-ups on EncounterDetail (#3572)."""

from django.test import TestCase
from drf_spectacular.drainage import get_override
from rest_framework.serializers import ListSerializer

from world.combat.constants import WINDUP_FIZZLE_DOWNGRADES
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import PendingOpponentAttack
from world.combat.serializers import EncounterDetailSerializer


def _serialize(encounter: object) -> dict:
    if not hasattr(encounter, "participants_cached"):
        encounter.participants_cached = list(encounter.participants.all())
    if not hasattr(encounter, "opponents_cached"):
        encounter.opponents_cached = list(encounter.opponents.all())
    return EncounterDetailSerializer(encounter, context={}).data


class PendingAttackSerializerTests(TestCase):
    def setUp(self) -> None:
        self.enc = CombatEncounterFactory(round_number=2)
        pool = ThreatPoolFactory()
        self.entry = ThreatPoolEntryFactory(pool=pool, windup_rounds=2)
        self.opp = CombatOpponentFactory(encounter=self.enc, threat_pool=pool, name="Ogre")
        self.part = CombatParticipantFactory(encounter=self.enc)

    def _pending(self, **overrides: object) -> PendingOpponentAttack:
        fields = {
            "encounter": self.enc,
            "opponent": self.opp,
            "threat_entry": self.entry,
            "target": self.part,
            "declared_round": 1,
            "resolves_round": 3,
        }
        fields.update(overrides)
        return PendingOpponentAttack.objects.create(**fields)

    def test_rows_carry_target_rounds_and_downgrade_scale(self) -> None:
        self._pending(downgrades=1, called_out=True)
        row = _serialize(self.enc)["pending_attacks"][0]
        self.assertEqual(row["opponent_id"], self.opp.pk)
        self.assertEqual(row["opponent_name"], "Ogre")
        self.assertEqual(row["target_participant_id"], self.part.pk)
        self.assertEqual(row["target_name"], str(self.part.character_sheet.character))
        self.assertEqual(row["declared_round"], 1)
        self.assertEqual(row["resolves_round"], 3)
        self.assertEqual(row["rounds_until_landing"], 1)
        self.assertEqual(row["downgrades"], 1)
        self.assertTrue(row["called_out"])
        self.assertAlmostEqual(row["damage_scale"], 0.75)
        self.assertFalse(row["cancelled"])

    def test_no_target_and_cancelled_at_fizzle_threshold(self) -> None:
        self._pending(target=None, downgrades=WINDUP_FIZZLE_DOWNGRADES)
        row = _serialize(self.enc)["pending_attacks"][0]
        self.assertIsNone(row["target_participant_id"])
        self.assertIsNone(row["target_name"])
        self.assertTrue(row["cancelled"])
        self.assertAlmostEqual(row["damage_scale"], 0.25)

    def test_rounds_until_landing_floors_at_zero(self) -> None:
        self._pending(declared_round=1, resolves_round=2)  # encounter is on round 2
        row = _serialize(self.enc)["pending_attacks"][0]
        self.assertEqual(row["rounds_until_landing"], 0)

    def test_empty_when_nothing_pending(self) -> None:
        self.assertEqual(_serialize(self.enc)["pending_attacks"], [])

    def test_field_is_schema_typed(self) -> None:
        override = get_override(EncounterDetailSerializer.get_pending_attacks, "field")
        self.assertIsInstance(override, ListSerializer)
