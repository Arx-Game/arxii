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
    ConditionPreApplyPayload,
    DamagePreApplyPayload,
    DamageSource,
)
from flows.factories import FlowDefinitionFactory, FlowStepDefinitionFactory
from world.conditions.factories import (
    ConditionCategoryFactory,
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
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


# ---------------------------------------------------------------------------
# Task 34: condition-specific protection (Tests 5-7)
# ---------------------------------------------------------------------------


class CharmImmunityAmuletTest(TestCase):
    """Test 5: Charm-immunity amulet — cancels mind_control category conditions only."""

    def setUp(self):
        self.target = CharacterFactory()
        self.target.location = _create_room()
        cancel_flow = _make_cancel_flow()
        # Filter: template.category.name == "mind_control"
        ReactiveConditionFactory(
            event_name=EventNames.CONDITION_PRE_APPLY,
            scope=TriggerScope.PERSONAL,
            filter_condition={
                "path": "template.category.name",
                "op": "==",
                "value": "mind_control",
            },
            flow_definition=cancel_flow,
            target=self.target,
        )

    def _dispatch(self, category_name: str):
        category = ConditionCategoryFactory(name=category_name)
        template = ConditionTemplateFactory(category=category)
        payload = ConditionPreApplyPayload(
            target=self.target,
            template=template,
            source=None,
            stage=None,
        )
        return self.target.trigger_handler.dispatch(EventNames.CONDITION_PRE_APPLY, payload)

    def test_hit_mind_control_cancels(self):
        result = self._dispatch("mind_control")
        self.assertTrue(result.cancelled)
        self.assertTrue(len(result.fired) > 0)

    def test_near_miss_buff_passes(self):
        result = self._dispatch("buff")
        self.assertFalse(result.cancelled)
        self.assertEqual(result.fired, [])


class CurseResistanceBySourceTest(TestCase):
    """Test 6: Curse-resistance by source — blocks scar-sourced withering only."""

    def setUp(self):
        self.target = CharacterFactory()
        self.target.location = _create_room()
        cancel_flow = _make_cancel_flow()
        # Filter: template.name == "withering" AND source.type == "scar"
        ReactiveConditionFactory(
            event_name=EventNames.CONDITION_PRE_APPLY,
            scope=TriggerScope.PERSONAL,
            filter_condition={
                "and": [
                    {"path": "template.name", "op": "==", "value": "withering"},
                    {"path": "source.type", "op": "==", "value": "scar"},
                ]
            },
            flow_definition=cancel_flow,
            target=self.target,
        )

    def test_hit_scar_sourced_withering_cancelled(self):
        template = ConditionTemplateFactory(name="withering")
        source = DamageSource(type="scar", ref=None)
        payload = ConditionPreApplyPayload(
            target=self.target,
            template=template,
            source=source,
            stage=None,
        )
        result = self.target.trigger_handler.dispatch(EventNames.CONDITION_PRE_APPLY, payload)
        self.assertTrue(result.cancelled)

    def test_near_miss_item_sourced_withering_passes(self):
        template = ConditionTemplateFactory(name="withering")
        source = DamageSource(type="item", ref=None)
        payload = ConditionPreApplyPayload(
            target=self.target,
            template=template,
            source=source,
            stage=None,
        )
        result = self.target.trigger_handler.dispatch(EventNames.CONDITION_PRE_APPLY, payload)
        self.assertFalse(result.cancelled)
        self.assertEqual(result.fired, [])


class StageSpecificVulnerabilityTest(TestCase):
    """Test 7: Stage-specific vulnerability — trigger active only at the scoped stage."""

    def setUp(self):
        self.character = CharacterFactory()
        self.character.location = _create_room()

    def test_hit_trigger_active_at_correct_stage(self):
        """Trigger with source_stage set is active when condition is at that stage."""
        template = ConditionTemplateFactory(has_progression=True)
        stage = ConditionStageFactory(condition=template, stage_order=1, severity_threshold=3)
        condition_instance = ConditionInstanceFactory(
            target=self.character,
            condition=template,
            current_stage=stage,
            severity=5,
        )
        cancel_flow = _make_cancel_flow()
        from flows.factories import TriggerDefinitionFactory, TriggerFactory
        from flows.models.events import Event

        event = Event.objects.get(name=EventNames.DAMAGE_PRE_APPLY)
        trigger_def = TriggerDefinitionFactory(event=event, flow_definition=cancel_flow)
        TriggerFactory(
            trigger_definition=trigger_def,
            obj=self.character,
            source_condition=condition_instance,
            source_stage=stage,
            scope=TriggerScope.PERSONAL,
            additional_filter_condition={},
        )

        payload = DamagePreApplyPayload(
            target=self.character,
            amount=10,
            damage_type="physical",
            source=DamageSource(type="character", ref=None),
        )
        result = self.character.trigger_handler.dispatch(EventNames.DAMAGE_PRE_APPLY, payload)
        self.assertTrue(result.cancelled)

    def test_near_miss_trigger_inactive_at_different_stage(self):
        """Stage-scoped trigger does NOT fire when condition is at a different stage."""
        template = ConditionTemplateFactory(has_progression=True)
        stage1 = ConditionStageFactory(condition=template, stage_order=1, severity_threshold=3)
        stage2 = ConditionStageFactory(condition=template, stage_order=2, severity_threshold=6)
        condition_instance = ConditionInstanceFactory(
            target=self.character,
            condition=template,
            current_stage=stage2,
            severity=7,
        )
        cancel_flow = _make_cancel_flow()
        from flows.factories import TriggerDefinitionFactory, TriggerFactory
        from flows.models.events import Event

        event = Event.objects.get(name=EventNames.DAMAGE_PRE_APPLY)
        trigger_def = TriggerDefinitionFactory(event=event, flow_definition=cancel_flow)
        # Trigger scoped to stage1 — should NOT fire because condition is at stage2
        TriggerFactory(
            trigger_definition=trigger_def,
            obj=self.character,
            source_condition=condition_instance,
            source_stage=stage1,
            scope=TriggerScope.PERSONAL,
            additional_filter_condition={},
        )

        payload = DamagePreApplyPayload(
            target=self.character,
            amount=10,
            damage_type="physical",
            source=DamageSource(type="character", ref=None),
        )
        result = self.character.trigger_handler.dispatch(EventNames.DAMAGE_PRE_APPLY, payload)
        self.assertFalse(result.cancelled)
        self.assertEqual(result.fired, [])


# ---------------------------------------------------------------------------
# Task 35: cross-character specificity (Tests 8-9)
# ---------------------------------------------------------------------------


class BondedEnemyRetaliationTest(TestCase):
    """Test 8: Bonded-enemy retaliation — fires only against specific bonded foes.

    Uses self.bonded_enemies on the defender (a plain list attribute) and the
    'in' operator to match the attacker's pk.
    """

    def setUp(self):
        self.defender = CharacterFactory()
        self.defender.location = _create_room()
        self.bonded_attacker = CharacterFactory()
        self.other_attacker = CharacterFactory()

        # Install bonded_enemies list on defender for self-reference in filter
        self.defender.bonded_enemies = [self.bonded_attacker.pk]

        cancel_flow = _make_cancel_flow()
        # Filter: source.ref.pk in self.bonded_enemies
        ReactiveConditionFactory(
            event_name=EventNames.DAMAGE_PRE_APPLY,
            scope=TriggerScope.PERSONAL,
            filter_condition={
                "path": "source.ref.pk",
                "op": "in",
                "value": "self.bonded_enemies",
            },
            flow_definition=cancel_flow,
            target=self.defender,
        )

    def test_hit_bonded_enemy_fires(self):
        payload = DamagePreApplyPayload(
            target=self.defender,
            amount=10,
            damage_type="physical",
            source=DamageSource(type="character", ref=self.bonded_attacker),
        )
        result = self.defender.trigger_handler.dispatch(EventNames.DAMAGE_PRE_APPLY, payload)
        self.assertTrue(result.cancelled)

    def test_near_miss_unbound_attacker_passes(self):
        payload = DamagePreApplyPayload(
            target=self.defender,
            amount=10,
            damage_type="physical",
            source=DamageSource(type="character", ref=self.other_attacker),
        )
        result = self.defender.trigger_handler.dispatch(EventNames.DAMAGE_PRE_APPLY, payload)
        self.assertFalse(result.cancelled)
        self.assertEqual(result.fired, [])


class CovenantAllegianceFilterTest(TestCase):
    """Test 9: Covenant-allegiance filter — fires on outsider attackers, not intra-covenant.

    Skipped: covenant relationship model does not yet exist.
    Retaliation filter `attacker.covenant != self.covenant` requires a covenant
    attribute on Character/ObjectDB which is not yet wired.
    """

    def test_covenant_filter_skipped(self):
        self.skipTest(
            "Covenant model not yet built; attacker.covenant path unresolvable. "
            "Implement when covenant system is added."
        )


# ---------------------------------------------------------------------------
# Task 36: payload-modifier specificity (Tests 10-11)
# ---------------------------------------------------------------------------


class ElementalConversionTest(TestCase):
    """Test 10: Elemental conversion — cold becomes fire (weakened) via MODIFY_PAYLOAD.

    A two-step flow: first sets damage_type="fire", then multiplies amount by 0.5.
    The trigger only fires on damage_type == "cold".
    """

    def setUp(self):
        self.character = CharacterFactory()
        self.character.location = _create_room()

        flow = FlowDefinitionFactory()
        # Step 1: set damage_type = "fire"
        step1 = FlowStepDefinitionFactory(
            flow=flow,
            parent_id=None,
            action=FlowActionChoices.MODIFY_PAYLOAD,
            parameters={"field": "damage_type", "op": "set", "value": "fire"},
        )
        # Step 2 (child of step1): multiply amount by 0.5
        FlowStepDefinitionFactory(
            flow=flow,
            parent_id=step1.pk,
            action=FlowActionChoices.MODIFY_PAYLOAD,
            parameters={"field": "amount", "op": "multiply", "value": 0.5},
        )

        ReactiveConditionFactory(
            event_name=EventNames.DAMAGE_PRE_APPLY,
            scope=TriggerScope.PERSONAL,
            filter_condition={"path": "damage_type", "op": "==", "value": "cold"},
            flow_definition=flow,
            target=self.character,
        )

    def test_hit_cold_converted_to_fire(self):
        payload = DamagePreApplyPayload(
            target=self.character,
            amount=20,
            damage_type="cold",
            source=DamageSource(type="technique", ref=None),
        )
        self.character.trigger_handler.dispatch(EventNames.DAMAGE_PRE_APPLY, payload)
        self.assertEqual(payload.damage_type, "fire")
        self.assertEqual(payload.amount, 10.0)

    def test_near_miss_fire_not_converted(self):
        payload = DamagePreApplyPayload(
            target=self.character,
            amount=20,
            damage_type="fire",
            source=DamageSource(type="technique", ref=None),
        )
        self.character.trigger_handler.dispatch(EventNames.DAMAGE_PRE_APPLY, payload)
        # Trigger filter didn't match — payload unchanged
        self.assertEqual(payload.damage_type, "fire")
        self.assertEqual(payload.amount, 20)


class ConditionalIntensityCapTest(TestCase):
    """Test 11: Conditional intensity cap — evocation amount > 50 capped to 50.

    MODIFY_PAYLOAD supports set/multiply/add ops but not 'min'. A proper intensity
    cap requires either a 'min' op or a payload-path conditional step. This test
    verifies that the near-miss (non-evocation) case passes through unchanged, and
    documents the cap-hit case as a known skip pending MODIFY_PAYLOAD 'min' op.
    """

    def setUp(self):
        self.character = CharacterFactory()
        self.character.location = _create_room()
        cancel_flow = _make_cancel_flow()
        # Filter fires on evocation school only
        ReactiveConditionFactory(
            event_name=EventNames.DAMAGE_PRE_APPLY,
            scope=TriggerScope.PERSONAL,
            filter_condition={
                "path": "source.ref.school",
                "op": "==",
                "value": "evocation",
            },
            flow_definition=cancel_flow,
            target=self.character,
        )

    def test_hit_evocation_filter_matches(self):
        """Evocation school source matches the filter and trigger fires.

        Skipped: no 'min' op on MODIFY_PAYLOAD means we cannot implement the
        cap within existing flow primitives. The test records the intent.
        """
        self.skipTest(
            "MODIFY_PAYLOAD lacks a 'min' op needed for intensity capping. "
            "Add 'min'/'max' ops to _execute_modify_payload, then implement "
            "cap as: {field: 'amount', op: 'min', value: 50}."
        )

    def test_near_miss_enchantment_uncapped(self):
        """Non-evocation source does not match the filter — amount unchanged."""
        payload = DamagePreApplyPayload(
            target=self.character,
            amount=100,
            damage_type="arcane",
            source=DamageSource(type="technique", ref=SimpleNamespace(school="enchantment")),
        )
        self.character.trigger_handler.dispatch(EventNames.DAMAGE_PRE_APPLY, payload)
        self.assertEqual(payload.amount, 100)
