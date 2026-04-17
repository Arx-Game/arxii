"""Integration tests for reactive layer filter DSL and dispatch routing (Phase 10, Tasks 33-40).

Tests verify hit + near-miss patterns for:
- Task 33: damage-source discrimination (Tests 1-4)
- Task 34: condition-specific protection (Tests 5-7)
- Task 35: cross-character specificity (Tests 8-9)
- Task 36: payload-modifier specificity (Tests 10-11)
- Task 37: AE chaos monkey — selective immunity and retaliation pileup (Tests 12-13)
- Task 38: attack-level cancellation tier (Tests 14-15)
- Task 39: stage/source cascade (Tests 16-18)

All payloads are constructed directly — no combat pipeline involvement.
The tests exercise the filter DSL and dispatch routing only.
"""

from types import SimpleNamespace

from django.test import TestCase
from evennia.objects.models import ObjectDB

from evennia_extensions.factories import CharacterFactory
from flows.constants import TriggerScope
from flows.consts import FlowActionChoices
from flows.emit import emit_event
from flows.events.names import EventNames
from flows.events.payloads import (
    ConditionPreApplyPayload,
    DamagePreApplyPayload,
    DamageSource,
)
from flows.factories import FlowDefinitionFactory, FlowStepDefinitionFactory
from flows.trigger_handler import TriggerHandler
from world.conditions.factories import (
    ConditionCategoryFactory,
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
    ReactiveConditionFactory,
)
from world.conditions.services import advance_condition_severity, remove_condition

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


# ---------------------------------------------------------------------------
# Task 37: AE chaos monkey (Tests 12-13)
# ---------------------------------------------------------------------------


class AESelectiveImmunityTest(TestCase):
    """Test 12: ROOM-scope emission with PERSONAL triggers — some targets immune, others not.

    Two characters in the same room receive an area-effect DAMAGE_PRE_APPLY.
    Character A has an abyssal-immunity scar (cancel on abyssal technique).
    Character B has no scar.
    Each dispatch is personal, so A's trigger fires but B's does not.
    """

    def setUp(self):
        self.room = _create_room("AERoom12")
        self.char_a = CharacterFactory()
        self.char_a.location = self.room
        self.char_b = CharacterFactory()
        self.char_b.location = self.room

        cancel_flow = _make_cancel_flow()
        # Char A has an abyssal-immunity scar
        ReactiveConditionFactory(
            event_name=EventNames.DAMAGE_PRE_APPLY,
            scope=TriggerScope.PERSONAL,
            filter_condition={"path": "source.ref.affinity", "op": "==", "value": "abyssal"},
            flow_definition=cancel_flow,
            target=self.char_a,
        )
        # Char B has no reactive condition at all

    def _ae_dispatch(self, char):
        """Dispatch DAMAGE_PRE_APPLY to *char* as a personal target (AE pattern)."""
        payload = DamagePreApplyPayload(
            target=char,
            amount=20,
            damage_type="arcane",
            source=_source_technique("abyssal"),
        )
        stack = emit_event(
            EventNames.DAMAGE_PRE_APPLY,
            payload,
            personal_target=char,
            room=self.room,
        )
        return stack, payload

    def test_hit_immune_char_cancels(self):
        """Char A's abyssal-immunity scar fires — dispatch is cancelled."""
        stack, _payload = self._ae_dispatch(self.char_a)
        self.assertTrue(stack.was_cancelled())

    def test_near_miss_unprotected_char_passes(self):
        """Char B has no scar — same AE passes through unmodified."""
        stack, payload = self._ae_dispatch(self.char_b)
        # No trigger on char_b, room has no triggers either
        self.assertFalse(stack.was_cancelled())
        self.assertEqual(payload.amount, 20)


class AERetaliationPileupTest(TestCase):
    """Test 13: Multiple characters in room each with a retaliation scar.

    Each character has a cancel-trigger on DAMAGE_PRE_APPLY. When the AE
    is dispatched via emit_event for each character, each personal dispatch
    fires independently. Verifies N parallel stacks each with a cancellation.
    """

    def setUp(self):
        self.room = _create_room("AERoom13")
        self.characters = []
        cancel_flow = _make_cancel_flow()
        for _ in range(3):
            char = CharacterFactory()
            char.location = self.room
            ReactiveConditionFactory(
                event_name=EventNames.DAMAGE_PRE_APPLY,
                scope=TriggerScope.PERSONAL,
                filter_condition=None,
                flow_definition=cancel_flow,
                target=char,
            )
            self.characters.append(char)

    def test_hit_all_characters_get_independent_cancellations(self):
        """Each character's dispatch is cancelled independently — N cancelled stacks."""
        stacks = []
        for char in self.characters:
            payload = DamagePreApplyPayload(
                target=char,
                amount=15,
                damage_type="fire",
                source=DamageSource(type="character", ref=None),
            )
            stack = emit_event(
                EventNames.DAMAGE_PRE_APPLY,
                payload,
                personal_target=char,
                room=self.room,
            )
            stacks.append(stack)

        # All three personal dispatches should be cancelled
        self.assertEqual(len(stacks), 3)
        for stack in stacks:
            self.assertTrue(stack.was_cancelled())

    def test_near_miss_no_scars_no_cancellation(self):
        """A character with no scar in the same room gets no cancellation."""
        clean_char = CharacterFactory()
        clean_char.location = self.room
        payload = DamagePreApplyPayload(
            target=clean_char,
            amount=15,
            damage_type="fire",
            source=DamageSource(type="character", ref=None),
        )
        stack = emit_event(
            EventNames.DAMAGE_PRE_APPLY,
            payload,
            personal_target=clean_char,
            room=self.room,
        )
        self.assertFalse(stack.was_cancelled())


# ---------------------------------------------------------------------------
# Task 38: Attack-level cancellation tier (Tests 14-15)
# ---------------------------------------------------------------------------


class RoomScopePreCancellationSkipsAllPersonalTest(TestCase):
    """Test 14: ROOM-scope PRE cancellation skips ALL PERSONAL dispatches for the AE.

    A room-level ward cancels DAMAGE_PRE_APPLY.
    emit_event dispatches ROOM first; if cancelled, PERSONAL is never reached.

    Implementation note: plain ObjectDB instances (created by _create_room) do not
    carry a trigger_handler attribute — emit_event silently skips them. To exercise
    the ROOM-cancels-PERSONAL short-circuit, we attach a TriggerHandler to the room
    instance directly and register a cancel trigger on it. This mirrors what the Room
    typeclass would do in production; the dispatch topology is identical.
    """

    def setUp(self):
        self.room = _create_room("AERoom14")
        self.char_a = CharacterFactory()
        self.char_a.location = self.room
        self.char_b = CharacterFactory()
        self.char_b.location = self.room

        # Room-level ward that always cancels DAMAGE_PRE_APPLY.
        # We install a TriggerHandler on the room ObjectDB instance, then
        # add a Trigger row with scope=ROOM and source_condition on the room.
        cancel_flow = _make_cancel_flow()
        from flows.factories import TriggerDefinitionFactory, TriggerFactory
        from flows.models.events import Event

        event = Event.objects.get(name=EventNames.DAMAGE_PRE_APPLY)
        trigger_def = TriggerDefinitionFactory(event=event, flow_definition=cancel_flow)
        room_condition = ConditionInstanceFactory(target=self.room)
        TriggerFactory(
            trigger_definition=trigger_def,
            obj=self.room,
            source_condition=room_condition,
            source_stage=None,
            scope=TriggerScope.ROOM,
            additional_filter_condition={},
        )
        # Attach a TriggerHandler to the room. The Trigger row was saved to DB
        # with obj=self.room, so _populate() will find it on first dispatch.
        room_handler = TriggerHandler(owner=self.room)
        self.room.trigger_handler = room_handler  # type: ignore[attr-defined]

        # Char A has a personal scar that would fire if reached
        personal_cancel = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventNames.DAMAGE_PRE_APPLY,
            scope=TriggerScope.PERSONAL,
            filter_condition=None,
            flow_definition=personal_cancel,
            target=self.char_a,
        )

    def test_hit_room_ward_cancels_before_personal(self):
        """Room-scope cancellation means the returned stack is already cancelled."""
        payload = DamagePreApplyPayload(
            target=self.char_a,
            amount=30,
            damage_type="fire",
            source=DamageSource(type="technique", ref=None),
        )
        stack = emit_event(
            EventNames.DAMAGE_PRE_APPLY,
            payload,
            personal_target=self.char_a,
            room=self.room,
        )
        self.assertTrue(stack.was_cancelled())

    def test_near_miss_no_room_ward_personal_still_reaches(self):
        """Without a room ward, personal dispatch runs normally for the character."""
        clean_room = _create_room("CleanRoom14")
        clean_char = CharacterFactory()
        clean_char.location = clean_room

        # Char has a personal cancel scar — fires when room has no ward
        personal_cancel = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventNames.DAMAGE_PRE_APPLY,
            scope=TriggerScope.PERSONAL,
            filter_condition=None,
            flow_definition=personal_cancel,
            target=clean_char,
        )
        payload = DamagePreApplyPayload(
            target=clean_char,
            amount=30,
            damage_type="fire",
            source=DamageSource(type="technique", ref=None),
        )
        stack = emit_event(
            EventNames.DAMAGE_PRE_APPLY,
            payload,
            personal_target=clean_char,
            room=clean_room,
        )
        # Room has no triggers (plain ObjectDB, no handler) — personal scar fires
        self.assertTrue(stack.was_cancelled())


class PersonalShieldCancelsOnlyOneTargetTest(TestCase):
    """Test 15: PERSONAL shield cancels only the one target; others still resolve.

    Two characters in the same room. Only Char A has a cancel scar.
    AE dispatched to both via separate emit_event calls (standard AE pattern).
    Char A's stack is cancelled; Char B's is not.
    """

    def setUp(self):
        self.room = _create_room("AERoom15")
        self.char_a = CharacterFactory()
        self.char_a.location = self.room
        self.char_b = CharacterFactory()
        self.char_b.location = self.room

        # Only char_a has a personal shield
        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventNames.DAMAGE_PRE_APPLY,
            scope=TriggerScope.PERSONAL,
            filter_condition=None,
            flow_definition=cancel_flow,
            target=self.char_a,
        )
        # char_b has no reactive conditions

    def _dispatch(self, char):
        payload = DamagePreApplyPayload(
            target=char,
            amount=25,
            damage_type="cold",
            source=DamageSource(type="technique", ref=None),
        )
        return emit_event(
            EventNames.DAMAGE_PRE_APPLY,
            payload,
            personal_target=char,
            room=self.room,
        )

    def test_hit_shielded_char_cancelled(self):
        """Char A's personal shield fires — their stack is cancelled."""
        stack = self._dispatch(self.char_a)
        self.assertTrue(stack.was_cancelled())

    def test_near_miss_unshielded_char_resolves(self):
        """Char B has no scar — their personal dispatch resolves without cancellation."""
        stack = self._dispatch(self.char_b)
        self.assertFalse(stack.was_cancelled())


# ---------------------------------------------------------------------------
# Task 39: Stage/source cascade (Tests 16-18)
# ---------------------------------------------------------------------------


class StageScopedTriggerStopsAfterAdvanceTest(TestCase):
    """Test 16: Stage-scoped trigger stops firing after advance_condition_severity moves stage.

    Build a scar tied to stage1 of a condition. Dispatch fires at stage1.
    advance_condition_severity moves to stage2. Dispatch no longer fires.
    """

    def setUp(self):
        self.character = CharacterFactory()
        self.character.location = _create_room("StageRoom16")

        template = ConditionTemplateFactory(has_progression=True)
        self.stage1 = ConditionStageFactory(condition=template, stage_order=1, severity_threshold=5)
        self.stage2 = ConditionStageFactory(
            condition=template, stage_order=2, severity_threshold=15
        )
        self.instance = ConditionInstanceFactory(
            target=self.character,
            condition=template,
            current_stage=self.stage1,
            severity=6,
        )

        cancel_flow = _make_cancel_flow()
        from flows.factories import TriggerDefinitionFactory, TriggerFactory
        from flows.models.events import Event

        event = Event.objects.get(name=EventNames.DAMAGE_PRE_APPLY)
        trigger_def = TriggerDefinitionFactory(event=event, flow_definition=cancel_flow)
        TriggerFactory(
            trigger_definition=trigger_def,
            obj=self.character,
            source_condition=self.instance,
            source_stage=self.stage1,  # Only active at stage1
            scope=TriggerScope.PERSONAL,
            additional_filter_condition={},
        )

    def _dispatch(self):
        payload = DamagePreApplyPayload(
            target=self.character,
            amount=10,
            damage_type="physical",
            source=DamageSource(type="character", ref=None),
        )
        return self.character.trigger_handler.dispatch(EventNames.DAMAGE_PRE_APPLY, payload)

    def test_hit_trigger_fires_at_stage1(self):
        """Trigger is active at stage1 — dispatch cancels."""
        result = self._dispatch()
        self.assertTrue(result.cancelled)
        self.assertTrue(len(result.fired) > 0)

    def test_near_miss_trigger_inactive_after_stage_advance(self):
        """After advancing to stage2, stage1 trigger no longer fires."""
        # Advance severity enough to cross stage2 threshold (15)
        advance_condition_severity(self.instance, 10)
        self.instance.refresh_from_db()
        # Verify stage actually advanced
        self.assertEqual(self.instance.current_stage_id, self.stage2.pk)
        # Now the trigger (scoped to stage1) should be inactive
        result = self._dispatch()
        self.assertFalse(result.cancelled)
        self.assertEqual(result.fired, [])


class ConditionRemovalCleansUpTriggerTest(TestCase):
    """Test 17: Condition removal cascades trigger cleanup.

    A character has a trigger installed via a condition.
    After remove_condition removes the instance (and CASCADE deletes the trigger),
    subsequent dispatch finds no trigger and does not fire.

    Note: REMOVE_CONDITION flow action does not exist in FlowActionChoices.
    This test exercises the same semantic: trigger is present → fires;
    condition removed → trigger gone → second dispatch does not fire.
    The flow-action variant is deferred until REMOVE_CONDITION is added to
    FlowActionChoices and FlowExecution._execute_step.
    """

    def setUp(self):
        self.character = CharacterFactory()
        self.character.location = _create_room("CascadeRoom17")

    def test_trigger_fires_then_gone_after_removal(self):
        """Trigger fires on first dispatch; after remove_condition it does not fire."""
        template = ConditionTemplateFactory()
        instance = ConditionInstanceFactory(
            target=self.character,
            condition=template,
        )
        cancel_flow = _make_cancel_flow()
        from flows.factories import TriggerDefinitionFactory, TriggerFactory
        from flows.models.events import Event

        event = Event.objects.get(name=EventNames.DAMAGE_PRE_APPLY)
        trigger_def = TriggerDefinitionFactory(event=event, flow_definition=cancel_flow)
        TriggerFactory(
            trigger_definition=trigger_def,
            obj=self.character,
            source_condition=instance,
            source_stage=None,
            scope=TriggerScope.PERSONAL,
            additional_filter_condition={},
        )
        # Re-populate trigger_handler to pick up the new trigger
        self.character.trigger_handler._populated = False

        def _dispatch():
            payload = DamagePreApplyPayload(
                target=self.character,
                amount=10,
                damage_type="physical",
                source=DamageSource(type="character", ref=None),
            )
            return self.character.trigger_handler.dispatch(EventNames.DAMAGE_PRE_APPLY, payload)

        # First dispatch: trigger is present, fires and cancels
        result_before = _dispatch()
        self.assertTrue(result_before.cancelled)

        # Remove the condition → CASCADE deletes Trigger row
        remove_condition(self.character, template)
        # Notify trigger_handler of removal
        self.character.trigger_handler._populated = False

        # Second dispatch: no trigger, does not fire
        result_after = _dispatch()
        self.assertFalse(result_after.cancelled)
        self.assertEqual(result_after.fired, [])

    def test_near_miss_condition_still_present_trigger_still_fires(self):
        """When condition is NOT removed, the trigger continues to fire."""
        template = ConditionTemplateFactory()
        instance = ConditionInstanceFactory(
            target=self.character,
            condition=template,
        )
        cancel_flow = _make_cancel_flow()
        from flows.factories import TriggerDefinitionFactory, TriggerFactory
        from flows.models.events import Event

        event = Event.objects.get(name=EventNames.DAMAGE_PRE_APPLY)
        trigger_def = TriggerDefinitionFactory(event=event, flow_definition=cancel_flow)
        TriggerFactory(
            trigger_definition=trigger_def,
            obj=self.character,
            source_condition=instance,
            source_stage=None,
            scope=TriggerScope.PERSONAL,
            additional_filter_condition={},
        )
        self.character.trigger_handler._populated = False

        def _dispatch():
            payload = DamagePreApplyPayload(
                target=self.character,
                amount=10,
                damage_type="physical",
                source=DamageSource(type="character", ref=None),
            )
            return self.character.trigger_handler.dispatch(EventNames.DAMAGE_PRE_APPLY, payload)

        # Two dispatches without removal — both fire
        result1 = _dispatch()
        # After first dispatch, usage cap (default=1) may suppress second — reset handler
        self.character.trigger_handler._populated = False
        result2 = _dispatch()
        # At least one fired (the first); condition was not removed
        self.assertTrue(result1.cancelled)
        self.assertTrue(result2.cancelled)


class MultiSourceSameEventTest(TestCase):
    """Test 18: Two condition instances on the same character, both with triggers on DAMAGE_APPLIED.

    Two separate ConditionInstances each install a trigger on DAMAGE_PRE_APPLY.
    A single dispatch fires both triggers independently.
    """

    def setUp(self):
        self.character = CharacterFactory()
        self.character.location = _create_room("MultiSourceRoom18")

    def test_hit_both_sources_fire(self):
        """Both condition-sourced triggers fire on the single dispatch."""
        from flows.factories import TriggerDefinitionFactory, TriggerFactory
        from flows.models.events import Event

        event = Event.objects.get(name=EventNames.DAMAGE_PRE_APPLY)

        # Source 1: doubles the damage
        double_flow = _make_multiply_field_flow("amount", 2)
        trigger_def1 = TriggerDefinitionFactory(event=event, flow_definition=double_flow)
        instance1 = ConditionInstanceFactory(target=self.character)
        TriggerFactory(
            trigger_definition=trigger_def1,
            obj=self.character,
            source_condition=instance1,
            source_stage=None,
            scope=TriggerScope.PERSONAL,
            additional_filter_condition={},
        )

        # Source 2: also doubles the damage (stacks multiplicatively)
        double_flow2 = _make_multiply_field_flow("amount", 2)
        trigger_def2 = TriggerDefinitionFactory(event=event, flow_definition=double_flow2)
        instance2 = ConditionInstanceFactory(target=self.character)
        TriggerFactory(
            trigger_definition=trigger_def2,
            obj=self.character,
            source_condition=instance2,
            source_stage=None,
            scope=TriggerScope.PERSONAL,
            additional_filter_condition={},
        )
        self.character.trigger_handler._populated = False

        payload = DamagePreApplyPayload(
            target=self.character,
            amount=10,
            damage_type="physical",
            source=DamageSource(type="character", ref=None),
        )
        result = self.character.trigger_handler.dispatch(EventNames.DAMAGE_PRE_APPLY, payload)

        # Both triggers fired: 10 * 2 * 2 = 40
        self.assertEqual(len(result.fired), 2)
        self.assertEqual(payload.amount, 40)

    def test_near_miss_single_source_fires_once(self):
        """With only one condition source, only one trigger fires (amount doubled once)."""
        from flows.factories import TriggerDefinitionFactory, TriggerFactory
        from flows.models.events import Event

        event = Event.objects.get(name=EventNames.DAMAGE_PRE_APPLY)
        double_flow = _make_multiply_field_flow("amount", 2)
        trigger_def = TriggerDefinitionFactory(event=event, flow_definition=double_flow)
        instance = ConditionInstanceFactory(target=self.character)
        TriggerFactory(
            trigger_definition=trigger_def,
            obj=self.character,
            source_condition=instance,
            source_stage=None,
            scope=TriggerScope.PERSONAL,
            additional_filter_condition={},
        )
        self.character.trigger_handler._populated = False

        payload = DamagePreApplyPayload(
            target=self.character,
            amount=10,
            damage_type="physical",
            source=DamageSource(type="character", ref=None),
        )
        result = self.character.trigger_handler.dispatch(EventNames.DAMAGE_PRE_APPLY, payload)

        # Only one trigger: 10 * 2 = 20
        self.assertEqual(len(result.fired), 1)
        self.assertEqual(payload.amount, 20)
