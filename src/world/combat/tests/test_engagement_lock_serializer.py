"""Tests for engagement lock serialization in encounter state (#2020)."""

from django.test import TestCase
from drf_spectacular.drainage import get_override
from rest_framework.serializers import ListSerializer

from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    EngagementLockFactory,
)
from world.combat.serializers import EncounterDetailSerializer, EngagementLockSerializer


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


class EngagementLockSchemaTypingTests(TestCase):
    """Regression guard for #3386: ``get_engagement_locks`` stays schema-typed.

    Without ``@extend_schema_field``, drf-spectacular emits
    ``{[key: string]: unknown}[]`` for this field (a regression can't be caught
    by ``test_serializer_includes_engagement_locks`` above, which only checks
    the runtime dict shape) — assert the schema override survives.
    """

    def test_get_engagement_locks_carries_extend_schema_field_override(self):
        method = EncounterDetailSerializer.get_engagement_locks
        field_override = get_override(method, "field")
        self.assertIsNotNone(field_override)
        # many=True: extend_schema_field(EngagementLockSerializer(many=True)) yields
        # a ListSerializer wrapping the child (DRF's many_init special-case).
        self.assertIsInstance(field_override, ListSerializer)
        self.assertIsInstance(field_override.child, EngagementLockSerializer)
