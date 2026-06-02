"""Tests for scar-gated MOVED triggers — Issue #526."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, RoomProfileFactory
from flows.constants import EventName
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.services import apply_condition
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


class WireScarEscalationTriggerTest(TestCase):
    """wire_scar_escalation_trigger links a MOVED TriggerDefinition to a scar template."""

    def test_trigger_definition_in_reactive_triggers(self):
        """After wiring, the scar template has a MOVED TriggerDefinition in reactive_triggers."""
        from flows.constants import EventName
        from world.magic.factories import wire_scar_escalation_trigger

        scar_template = ConditionTemplateFactory(name="abyssal_scar_526")
        escalation_template = ConditionTemplateFactory(name="hallowed_agony_526")

        wire_scar_escalation_trigger(
            scar_template=scar_template,
            escalation_template=escalation_template,
            hostile_affinity_name="Celestial",
        )

        trigger_defs = list(scar_template.reactive_triggers.all())
        self.assertEqual(len(trigger_defs), 1)
        td = trigger_defs[0]
        self.assertEqual(td.event_name, EventName.MOVED)
        self.assertEqual(
            td.base_filter_condition,
            {"path": "destination.dominant_affinity.name", "op": "==", "value": "Celestial"},
        )

    def test_wiring_is_idempotent(self):
        """Calling wire_scar_escalation_trigger twice doesn't duplicate rows."""
        from world.magic.factories import wire_scar_escalation_trigger

        scar_template = ConditionTemplateFactory(name="abyssal_scar_526b")
        escalation_template = ConditionTemplateFactory(name="hallowed_agony_526b")

        wire_scar_escalation_trigger(
            scar_template=scar_template,
            escalation_template=escalation_template,
            hostile_affinity_name="Celestial",
        )
        wire_scar_escalation_trigger(
            scar_template=scar_template,
            escalation_template=escalation_template,
            hostile_affinity_name="Celestial",
        )

        self.assertEqual(scar_template.reactive_triggers.count(), 1)

    def test_trigger_installed_when_condition_applied(self):
        """Applying the scar condition auto-installs a Trigger row on the character."""
        from flows.models.triggers import Trigger
        from world.magic.factories import wire_scar_escalation_trigger

        scar_template = ConditionTemplateFactory(name="abyssal_scar_526c")
        escalation_template = ConditionTemplateFactory(name="hallowed_agony_526c")
        wire_scar_escalation_trigger(
            scar_template=scar_template,
            escalation_template=escalation_template,
            hostile_affinity_name="Celestial",
        )

        character = CharacterFactory()
        apply_condition(target=character, condition=scar_template)

        installed = Trigger.objects.filter(obj=character)
        self.assertEqual(installed.count(), 1)
        self.assertEqual(installed.first().trigger_definition.event_name, "moved")


class ScarMovedTriggerIntegrationTest(ResonanceCacheIsolationMixin, TestCase):
    """End-to-end: Abyssal-scarred character entering celestial-cascade room gets escalation.

    Full pipeline:
      apply_condition (installs Trigger) → at_post_move (emits MOVED) →
      trigger filter (destination.dominant_affinity.name == "Celestial526") →
      FlowDefinition (CALL_SERVICE_FUNCTION apply_condition_by_name) →
      escalation ConditionInstance created on character.
    """

    def setUp(self):
        super().setUp()  # clears AffinityInteraction cache — create rows AFTER

        from decimal import Decimal

        from world.magic.constants import (
            AffinityInteractionAggressor,
            AffinityInteractionKind,
            ResonanceValence,
        )
        from world.magic.factories import (
            AffinityFactory,
            AffinityInteractionFactory,
            ResonanceFactory,
            wire_scar_escalation_trigger,
        )
        from world.magic.services.gain import tag_room_resonance

        # -- Affinities --
        self.celestial = AffinityFactory(name="Celestial526")
        self.abyssal = AffinityFactory(name="Abyssal526")

        # -- Pair #4: Abyssal caster in Celestial room → OPPOSED/REJECT/environment aggressor
        AffinityInteractionFactory(
            source_affinity=self.abyssal,
            environment_affinity=self.celestial,
            valence=ResonanceValence.OPPOSED,
            kind=AffinityInteractionKind.REJECT,
            aggressor=AffinityInteractionAggressor.ENVIRONMENT,
            severity_multiplier=Decimal("1.00"),
        )

        # -- Celestial cascade room --
        self.celestial_res = ResonanceFactory(name="CelestialRes526b", affinity=self.celestial)
        self.celestial_profile = RoomProfileFactory()
        tag_room_resonance(self.celestial_profile, self.celestial_res)
        self.celestial_room = self.celestial_profile.objectdb

        # -- Abyssal (aligned for Abyssal scar) room --
        self.abyssal_res = ResonanceFactory(name="AbyssalRes526b", affinity=self.abyssal)
        self.abyssal_profile = RoomProfileFactory()
        tag_room_resonance(self.abyssal_profile, self.abyssal_res)
        self.abyssal_room = self.abyssal_profile.objectdb

        # -- Inert room --
        self.inert_profile = RoomProfileFactory()
        self.inert_room = self.inert_profile.objectdb

        # -- Character --
        self.character = CharacterFactory()

        # -- Scar + escalation condition templates --
        self.scar_template = ConditionTemplateFactory(name="AbyssalScar526")
        self.escalation_template = ConditionTemplateFactory(name="HallowedAgony526")

        # -- Wire the trigger --
        wire_scar_escalation_trigger(
            scar_template=self.scar_template,
            escalation_template=self.escalation_template,
            hostile_affinity_name="Celestial526",
        )

        # Apply scar → auto-installs the MOVED Trigger row
        apply_condition(target=self.character, condition=self.scar_template)

    def _escalation_count(self):
        from world.conditions.models import ConditionInstance

        return ConditionInstance.objects.filter(
            target=self.character,
            condition=self.escalation_template,
        ).count()

    def _place_in(self, room):
        """Set character.location without firing hooks (setup only)."""
        self.character.db_location = room
        self.character.save(update_fields=["db_location"])

    def test_abyssal_scar_in_celestial_room_applies_escalation(self):
        """Moving into a Celestial-cascade room applies the escalation condition."""
        self._place_in(self.celestial_room)
        self.character.at_post_move(source_location=self.inert_room)

        self.assertEqual(
            self._escalation_count(),
            1,
            "Expected escalation condition after entering celestial room with Abyssal scar",
        )

    def test_abyssal_scar_in_abyssal_room_no_escalation(self):
        """Moving into an Abyssal (aligned) room does NOT apply escalation."""
        self._place_in(self.abyssal_room)
        self.character.at_post_move(source_location=self.inert_room)

        self.assertEqual(self._escalation_count(), 0, "No escalation expected in Abyssal room")

    def test_abyssal_scar_in_inert_room_no_escalation(self):
        """Moving into an inert room (no cascade) does NOT apply escalation."""
        self._place_in(self.inert_room)
        self.character.at_post_move(source_location=self.celestial_room)

        self.assertEqual(self._escalation_count(), 0, "No escalation expected in inert room")

    def test_unscarred_character_no_escalation(self):
        """A character without the scar condition does not take escalation on entry."""
        from world.conditions.models import ConditionInstance

        clean_char = CharacterFactory()
        clean_char.db_location = self.celestial_room
        clean_char.save(update_fields=["db_location"])
        clean_char.at_post_move(source_location=self.inert_room)

        self.assertEqual(
            ConditionInstance.objects.filter(
                target=clean_char, condition=self.escalation_template
            ).count(),
            0,
            "Unscarred character should not receive escalation",
        )
