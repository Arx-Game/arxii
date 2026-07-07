"""Tests for engagement lock serialization in encounter state (#2020)."""

from django.test import TestCase

from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    EngagementLockFactory,
)
from world.combat.serializers import EncounterDetailSerializer


def _serialize(encounter: object) -> dict:
    """Set up cached attrs so the serializer doesn't fall back to DB queries."""
    if not hasattr(encounter, "participants_cached"):
        encounter.participants_cached = list(encounter.participants.all())
    if not hasattr(encounter, "opponents_cached"):
        encounter.opponents_cached = list(encounter.opponents.all())
    return EncounterDetailSerializer(encounter, context={}).data


class EngagementLockSerializerTests(TestCase):
    """EncounterDetailSerializer exposes active engagement locks."""

    def test_serializer_includes_engagement_locks(self):
        enc = CombatEncounterFactory()
        opp = CombatOpponentFactory(encounter=enc)
        part = CombatParticipantFactory(encounter=enc)
        EngagementLockFactory(encounter=enc, opponent=opp, participant=part)
        data = _serialize(enc)
        self.assertIn("engagement_locks", data)
        self.assertEqual(len(data["engagement_locks"]), 1)
        self.assertEqual(data["engagement_locks"][0]["opponent_id"], opp.pk)
        self.assertEqual(data["engagement_locks"][0]["participant_id"], part.pk)

    def test_no_locks_returns_empty_list(self):
        enc = CombatEncounterFactory()
        data = _serialize(enc)
        self.assertEqual(data["engagement_locks"], [])
