"""Integration tests for reactive layer filter DSL and dispatch routing (Phase 10, Tasks 33-36).

Tests verify hit + near-miss patterns for:
- Task 33: damage-source discrimination (Tests 1-4)
- Task 34: condition-specific protection (Tests 5-7)
- Task 35: cross-character specificity (Tests 8-9)
- Task 36: payload-modifier specificity (Tests 10-11)

All payloads are constructed directly — no combat pipeline involvement.
The tests exercise the filter DSL and dispatch routing only.
"""

from types import SimpleNamespace

from django.test import TestCase
from evennia.objects.models import ObjectDB

from evennia_extensions.factories import CharacterFactory
from flows.constants import TriggerScope
from flows.consts import FlowActionChoices
from flows.events.names import EventNames
from flows.events.payloads import (
    DamagePreApplyPayload,
    DamageSource,
)
from flows.factories import FlowDefinitionFactory, FlowStepDefinitionFactory
from world.conditions.factories import (
    ReactiveConditionFactory,
)

# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _create_room(key: str = "TestRoom") -> ObjectDB:
    return ObjectDB.objects.create(
        db_key=key,
        db_typeclass_path="typeclasses.rooms.Room",
    )


def _make_cancel_flow():
    """Return a FlowDefinition with a single CANCEL_EVENT step."""
    flow = FlowDefinitionFactory()
    FlowStepDefinitionFactory(
        flow=flow,
        parent_id=None,
        action=FlowActionChoices.CANCEL_EVENT,
        parameters={},
    )
    return flow


def _make_set_field_flow(field: str, value):
    """Return a FlowDefinition that sets payload.<field> to value."""
    flow = FlowDefinitionFactory()
    FlowStepDefinitionFactory(
        flow=flow,
        parent_id=None,
        action=FlowActionChoices.MODIFY_PAYLOAD,
        parameters={"field": field, "op": "set", "value": value},
    )
    return flow


def _make_multiply_field_flow(field: str, factor):
    """Return a FlowDefinition that multiplies payload.<field> by factor."""
    flow = FlowDefinitionFactory()
    FlowStepDefinitionFactory(
        flow=flow,
        parent_id=None,
        action=FlowActionChoices.MODIFY_PAYLOAD,
        parameters={"field": field, "op": "multiply", "value": factor},
    )
    return flow


def _source_technique(affinity_name: str = "abyssal"):
    """Return a DamageSource(type='technique', ref=<SimpleNamespace>) with affinity attribute.

    Technique → affinity path is too deep to walk via M2M in the filter DSL
    (gift.resonances is an M2M). We use a SimpleNamespace stub so the filter
    path 'source.ref.affinity' resolves cleanly via getattr.
    """
    ref = SimpleNamespace(affinity=affinity_name)
    return DamageSource(type="technique", ref=ref)


def _source_character_with_property(has_flesh: bool = True):
    """Return a DamageSource(type='character', ref=<stub>) with has_property method."""

    class _StubChar:
        def has_property(self, name: str) -> bool:
            if name == "flesh-and-blood":
                return has_flesh
            return False

    return DamageSource(type="character", ref=_StubChar())


def _source_with_weapon_tags(tags: list):
    """Return a DamageSource whose ref has a weapon attribute with .tags list."""
    ref = SimpleNamespace(weapon=SimpleNamespace(tags=tags))
    return DamageSource(type="character", ref=ref)


# ---------------------------------------------------------------------------
# Task 33: damage-source discrimination (Tests 1-4)
# ---------------------------------------------------------------------------


class AbyssalOnlyWardTest(TestCase):
    """Test 1: Abyssal-only ward — fires on abyssal technique, not on celestial."""

    def setUp(self):
        self.character = CharacterFactory()
        self.character.location = _create_room()
        cancel_flow = _make_cancel_flow()
        # Ward fires only when source.ref.affinity == "abyssal"
        ReactiveConditionFactory(
            event_name=EventNames.DAMAGE_PRE_APPLY,
            scope=TriggerScope.PERSONAL,
            filter_condition={"path": "source.ref.affinity", "op": "==", "value": "abyssal"},
            flow_definition=cancel_flow,
            target=self.character,
        )

    def _dispatch(self, affinity: str):
        payload = DamagePreApplyPayload(
            target=self.character,
            amount=10,
            damage_type="fire",
            source=_source_technique(affinity),
        )
        return self.character.trigger_handler.dispatch(EventNames.DAMAGE_PRE_APPLY, payload)

    def test_hit_abyssal_cancels(self):
        result = self._dispatch("abyssal")
        self.assertTrue(result.cancelled)
        self.assertTrue(len(result.fired) > 0)

    def test_near_miss_celestial_passes(self):
        result = self._dispatch("celestial")
        self.assertFalse(result.cancelled)
        self.assertEqual(result.fired, [])


class NotCelestialVulnerabilityTest(TestCase):
    """Test 2: Not-celestial vulnerability — fire damage from non-celestial source doubles."""

    def setUp(self):
        self.character = CharacterFactory()
        self.character.location = _create_room()
        double_flow = _make_multiply_field_flow("amount", 2)
        # Filter: damage_type == "fire" AND source.ref.affinity != "celestial"
        ReactiveConditionFactory(
            event_name=EventNames.DAMAGE_PRE_APPLY,
            scope=TriggerScope.PERSONAL,
            filter_condition={
                "and": [
                    {"path": "damage_type", "op": "==", "value": "fire"},
                    {"path": "source.ref.affinity", "op": "!=", "value": "celestial"},
                ]
            },
            flow_definition=double_flow,
            target=self.character,
        )

    def test_hit_abyssal_fire_doubles(self):
        payload = DamagePreApplyPayload(
            target=self.character,
            amount=10,
            damage_type="fire",
            source=_source_technique("abyssal"),
        )
        self.character.trigger_handler.dispatch(EventNames.DAMAGE_PRE_APPLY, payload)
        self.assertEqual(payload.amount, 20)

    def test_near_miss_celestial_fire_unchanged(self):
        payload = DamagePreApplyPayload(
            target=self.character,
            amount=10,
            damage_type="fire",
            source=_source_technique("celestial"),
        )
        self.character.trigger_handler.dispatch(EventNames.DAMAGE_PRE_APPLY, payload)
        self.assertEqual(payload.amount, 10)


class AttackerPropertyRequiredTest(TestCase):
    """Test 3: Attacker property required — fires on flesh-and-blood attackers only."""

    def setUp(self):
        self.character = CharacterFactory()
        self.character.location = _create_room()
        cancel_flow = _make_cancel_flow()
        # Filter: source.ref has_property "flesh-and-blood"
        ReactiveConditionFactory(
            event_name=EventNames.DAMAGE_PRE_APPLY,
            scope=TriggerScope.PERSONAL,
            filter_condition={
                "path": "source.ref",
                "op": "has_property",
                "value": "flesh-and-blood",
            },
            flow_definition=cancel_flow,
            target=self.character,
        )

    def test_hit_flesh_attacker_fires(self):
        payload = DamagePreApplyPayload(
            target=self.character,
            amount=10,
            damage_type="physical",
            source=_source_character_with_property(has_flesh=True),
        )
        result = self.character.trigger_handler.dispatch(EventNames.DAMAGE_PRE_APPLY, payload)
        self.assertTrue(result.cancelled)

    def test_near_miss_construct_does_not_fire(self):
        payload = DamagePreApplyPayload(
            target=self.character,
            amount=10,
            damage_type="physical",
            source=_source_character_with_property(has_flesh=False),
        )
        result = self.character.trigger_handler.dispatch(EventNames.DAMAGE_PRE_APPLY, payload)
        self.assertFalse(result.cancelled)
        self.assertEqual(result.fired, [])


class WeaponTagFilterTest(TestCase):
    """Test 4: Weapon-tag filter — werewolf-bane scar fires only on silvered hits."""

    def setUp(self):
        self.character = CharacterFactory()
        self.character.location = _create_room()
        cancel_flow = _make_cancel_flow()
        # Filter: source.ref.weapon.tags contains "silvered"
        ReactiveConditionFactory(
            event_name=EventNames.DAMAGE_PRE_APPLY,
            scope=TriggerScope.PERSONAL,
            filter_condition={
                "path": "source.ref.weapon.tags",
                "op": "contains",
                "value": "silvered",
            },
            flow_definition=cancel_flow,
            target=self.character,
        )

    def test_hit_silvered_weapon_fires(self):
        payload = DamagePreApplyPayload(
            target=self.character,
            amount=10,
            damage_type="physical",
            source=_source_with_weapon_tags(["silvered", "iron"]),
        )
        result = self.character.trigger_handler.dispatch(EventNames.DAMAGE_PRE_APPLY, payload)
        self.assertTrue(result.cancelled)

    def test_near_miss_iron_only_does_not_fire(self):
        payload = DamagePreApplyPayload(
            target=self.character,
            amount=10,
            damage_type="physical",
            source=_source_with_weapon_tags(["iron"]),
        )
        result = self.character.trigger_handler.dispatch(EventNames.DAMAGE_PRE_APPLY, payload)
        self.assertFalse(result.cancelled)
        self.assertEqual(result.fired, [])
