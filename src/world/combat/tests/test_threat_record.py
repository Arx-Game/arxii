"""Tests for the ThreatRecord model — per-(opponent, participant) threat (#2020)."""

from django.db import IntegrityError
from django.test import TestCase

from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatRecordFactory,
)
from world.combat.models import ThreatRecord


class ThreatRecordModelTests(TestCase):
    """ThreatRecord: one row per (encounter, opponent, participant)."""

    def test_defaults_to_zero_threat(self):
        record = ThreatRecordFactory()
        self.assertEqual(record.threat_value, 0)

    def test_str_representation(self):
        record = ThreatRecordFactory(threat_value=42)
        self.assertIn("42", str(record))

    def test_unique_per_pairing(self):
        record = ThreatRecordFactory()
        with self.assertRaises(IntegrityError):
            ThreatRecord.objects.create(
                encounter=record.encounter,
                opponent=record.opponent,
                participant=record.participant,
                threat_value=10,
            )

    def test_get_or_create_is_idempotent(self):
        from world.combat.services import get_or_create_threat_record

        enc = CombatEncounterFactory()
        opp = CombatOpponentFactory(encounter=enc)
        part = CombatParticipantFactory(encounter=enc)
        record = get_or_create_threat_record(enc, opp, part)
        record.threat_value = 50
        record.save()
        same = get_or_create_threat_record(enc, opp, part)
        self.assertEqual(same.pk, record.pk)
        self.assertEqual(same.threat_value, 50)

    def test_accumulate_threat_increments(self):
        from world.combat.services import accumulate_threat

        enc = CombatEncounterFactory()
        opp = CombatOpponentFactory(encounter=enc)
        part = CombatParticipantFactory(encounter=enc)
        accumulate_threat(enc, opp, part, 30)
        accumulate_threat(enc, opp, part, 15)
        record = ThreatRecord.objects.get(encounter=enc, opponent=opp, participant=part)
        self.assertEqual(record.threat_value, 45)
