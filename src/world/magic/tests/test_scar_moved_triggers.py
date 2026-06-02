"""Tests for scar-gated MOVED triggers — Issue #526."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, RoomProfileFactory
from flows.constants import EventName
from world.conditions.factories import ConditionTemplateFactory
from world.magic.tests._cache_isolation import ResonanceCacheIsolationMixin


class MovedEventEmissionTest(TestCase):
    """at_post_move emits EventName.MOVED so installed triggers fire."""

    def setUp(self):
        self.room = RoomProfileFactory().objectdb
        self.character = CharacterFactory()
        self.character.db_location = self.room
        self.character.save(update_fields=["db_location"])

    def test_at_post_move_emits_moved_event(self):
        """at_post_move calls emit_event with EventName.MOVED."""
        with patch("typeclasses.characters.emit_event") as mock_emit:
            mock_emit.return_value = MagicMock()
            self.character.at_post_move(source_location=None)

        calls = [c for c in mock_emit.call_args_list if c.args and c.args[0] == EventName.MOVED]
        self.assertTrue(
            len(calls) >= 1,
            "Expected emit_event(EventName.MOVED, ...) to be called from at_post_move",
        )


class RoomDominantAffinityTest(ResonanceCacheIsolationMixin, TestCase):
    """Room.dominant_affinity returns the cascade-dominant Affinity or None."""

    def setUp(self):
        super().setUp()
        from world.magic.factories import AffinityFactory, ResonanceFactory
        from world.magic.services.gain import tag_room_resonance

        self.celestial = AffinityFactory(name="Celestial")
        self.celestial_res = ResonanceFactory(name="CelestialRes526", affinity=self.celestial)

        self.celestial_profile = RoomProfileFactory()
        tag_room_resonance(self.celestial_profile, self.celestial_res)
        self.celestial_room = self.celestial_profile.objectdb

        self.inert_profile = RoomProfileFactory()
        self.inert_room = self.inert_profile.objectdb

    def test_cascade_room_returns_dominant_affinity(self):
        """Room with a celestial resonance tagged returns the Celestial affinity."""
        result = self.celestial_room.dominant_affinity
        self.assertIsNotNone(result)
        self.assertEqual(result.name, "Celestial")

    def test_inert_room_returns_none(self):
        """Room with no cascade resonances returns None."""
        result = self.inert_room.dominant_affinity
        self.assertIsNone(result)

    def test_dominant_affinity_name_navigable_in_filter_dsl(self):
        """Filter DSL can navigate destination.dominant_affinity.name at runtime."""
        from dataclasses import dataclass

        from flows.filters.evaluator import evaluate_filter

        @dataclass
        class StubPayload:
            destination: object

        payload = StubPayload(destination=self.celestial_room)
        filter_spec = {
            "path": "destination.dominant_affinity.name",
            "op": "==",
            "value": "Celestial",
        }
        self.assertTrue(evaluate_filter(filter_spec, payload, self_ref=None))

    def test_filter_dsl_non_matching_room_returns_false(self):
        """Filter DSL returns False when room affinity does not match the filter value."""
        from dataclasses import dataclass

        from flows.filters.evaluator import evaluate_filter

        @dataclass
        class StubPayload:
            destination: object

        payload = StubPayload(destination=self.inert_room)
        filter_spec = {
            "path": "destination.dominant_affinity.name",
            "op": "==",
            "value": "Celestial",
        }
        self.assertFalse(evaluate_filter(filter_spec, payload, self_ref=None))


class ApplyConditionByNameTest(TestCase):
    """apply_condition_by_name looks up a ConditionTemplate by name and applies it."""

    def setUp(self):
        from dataclasses import dataclass

        self.template = ConditionTemplateFactory(name="test_escalation_526")
        self.character = CharacterFactory()

        @dataclass
        class StubPayload:
            character: object

        self.payload = StubPayload(character=self.character)

    def test_applies_named_condition_to_payload_character(self):
        """apply_condition_by_name applies the condition to payload.character."""
        from world.conditions.models import ConditionInstance
        from world.conditions.services import apply_condition_by_name

        apply_condition_by_name(payload=self.payload, condition_name="test_escalation_526")

        count = ConditionInstance.objects.filter(
            target=self.character,
            condition=self.template,
        ).count()
        self.assertEqual(count, 1, "Expected one ConditionInstance after apply_condition_by_name")

    def test_silently_no_ops_when_condition_not_found(self):
        """apply_condition_by_name does nothing when the condition name doesn't exist."""
        from world.conditions.models import ConditionInstance
        from world.conditions.services import apply_condition_by_name

        apply_condition_by_name(payload=self.payload, condition_name="nonexistent_526")

        self.assertEqual(ConditionInstance.objects.filter(target=self.character).count(), 0)
