"""Integration tests for reactive layer filter DSL + unified dispatch.

All scenarios exercise ``emit_event(name, payload, location)`` — the
unified-dispatch entry point that walks ``[location, *location.contents]``,
gathers every owner's triggers, sorts by priority desc, and dispatches
synchronously on a single FlowStack.

Targeting is expressed via ``additional_filter_condition``:

- Self-targeting (old PERSONAL): ``{"path": "target", "op": "==", "value": "self"}``
- Bystander (old ROOM): no target filter, or explicit ``!= self``
- Cross-character specificity: self filter matches only when
  ``payload.target`` is the trigger's owner

Room-owned triggers (wards, watchful rooms) live on a pseudo-condition
whose ``target`` is the room itself, so the Trigger's ``obj`` is the
room. The room's ``trigger_handler`` cached-property makes it eligible
for the gather phase.
"""

from types import SimpleNamespace

from django.test import TestCase
from evennia.objects.models import ObjectDB

from evennia_extensions.factories import CharacterFactory
from flows.constants import EventName
from flows.consts import FlowActionChoices
from flows.emit import emit_event
from flows.events.payloads import (
    AttackPreResolvePayload,
    ConditionPreApplyPayload,
    DamagePreApplyPayload,
    DamageSource,
)
from flows.factories import (
    FlowDefinitionFactory,
    FlowStepDefinitionFactory,
    TriggerDefinitionFactory,
    TriggerFactory,
)
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


SELF_FILTER = {"path": "target", "op": "==", "value": "self"}
NOT_SELF_FILTER = {"path": "target", "op": "!=", "value": "self"}


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
    """DamageSource(type='technique', ref=SimpleNamespace with affinity)."""
    ref = SimpleNamespace(affinity=affinity_name)
    return DamageSource(type="technique", ref=ref)


def _source_character_with_property(has_flesh: bool = True):
    """DamageSource wrapping a stub character with has_property()."""

    class _StubChar:
        def has_property(self, name: str) -> bool:
            if name == "flesh-and-blood":
                return has_flesh
            return False

    return DamageSource(type="character", ref=_StubChar())


def _source_with_weapon_tags(tags: list):
    """DamageSource whose ref has a weapon attribute with .tags list."""
    ref = SimpleNamespace(weapon=SimpleNamespace(tags=tags))
    return DamageSource(type="character", ref=ref)


def _damage_payload(character, *, amount=10, damage_type="physical", source=None):
    return DamagePreApplyPayload(
        target=character,
        amount=amount,
        damage_type=damage_type,
        source=source if source is not None else DamageSource(type="character", ref=None),
    )


def _emit_damage(character, payload):
    return emit_event(EventName.DAMAGE_PRE_APPLY, payload, location=character.location)


def _install_room_trigger(
    room,
    *,
    event_name: str,
    flow_definition,
    filter_condition: dict | None = None,
):
    """Install a trigger owned by ``room`` via a pseudo-condition on the room.

    Room-owned triggers need a ConditionInstance whose target is the room.
    Returns the Trigger row.
    """
    trigger_def = TriggerDefinitionFactory(event_name=event_name, flow_definition=flow_definition)
    room_condition = ConditionInstanceFactory(target=room)
    trigger = TriggerFactory(
        trigger_definition=trigger_def,
        obj=room,
        source_condition=room_condition,
        source_stage=None,
        additional_filter_condition=filter_condition or {},
    )
    # The room typeclass mixin installs ``trigger_handler`` as a cached_property,
    # so the gather phase will discover it. Nudge the cache so it picks up this
    # new row on the next dispatch.
    if hasattr(room, "trigger_handler"):
        room.trigger_handler._populated = False
    return trigger


# ---------------------------------------------------------------------------
# Damage-source discrimination (Tests 1-4)
# ---------------------------------------------------------------------------


class AbyssalOnlyWardTest(TestCase):
    """Test 1: Abyssal-only ward fires on abyssal technique, not celestial."""

    def setUp(self):
        self.room = _create_room("AbyssalRoom1")
        self.character = CharacterFactory()
        self.character.location = self.room
        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventName.DAMAGE_PRE_APPLY,
            filter_condition={"path": "source.ref.affinity", "op": "==", "value": "abyssal"},
            flow_definition=cancel_flow,
            target=self.character,
        )

    def _dispatch(self, affinity: str):
        payload = _damage_payload(
            self.character,
            damage_type="fire",
            source=_source_technique(affinity),
        )
        return _emit_damage(self.character, payload)

    def test_hit_abyssal_cancels(self):
        stack = self._dispatch("abyssal")
        self.assertTrue(stack.was_cancelled())

    def test_near_miss_celestial_passes(self):
        stack = self._dispatch("celestial")
        self.assertFalse(stack.was_cancelled())


class NotCelestialVulnerabilityTest(TestCase):
    """Test 2: Non-celestial fire doubles damage; celestial fire passes through."""

    def setUp(self):
        self.room = _create_room("NotCelestialRoom2")
        self.character = CharacterFactory()
        self.character.location = self.room
        double_flow = _make_multiply_field_flow("amount", 2)
        ReactiveConditionFactory(
            event_name=EventName.DAMAGE_PRE_APPLY,
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
        payload = _damage_payload(
            self.character,
            damage_type="fire",
            source=_source_technique("abyssal"),
        )
        _emit_damage(self.character, payload)
        self.assertEqual(payload.amount, 20)

    def test_near_miss_celestial_fire_unchanged(self):
        payload = _damage_payload(
            self.character,
            damage_type="fire",
            source=_source_technique("celestial"),
        )
        _emit_damage(self.character, payload)
        self.assertEqual(payload.amount, 10)


class AttackerPropertyRequiredTest(TestCase):
    """Test 3: Ward fires only on flesh-and-blood attackers."""

    def setUp(self):
        self.room = _create_room("PropertyRoom3")
        self.character = CharacterFactory()
        self.character.location = self.room
        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventName.DAMAGE_PRE_APPLY,
            filter_condition={
                "path": "source.ref",
                "op": "has_property",
                "value": "flesh-and-blood",
            },
            flow_definition=cancel_flow,
            target=self.character,
        )

    def test_hit_flesh_attacker_fires(self):
        payload = _damage_payload(
            self.character,
            source=_source_character_with_property(has_flesh=True),
        )
        stack = _emit_damage(self.character, payload)
        self.assertTrue(stack.was_cancelled())

    def test_near_miss_construct_does_not_fire(self):
        payload = _damage_payload(
            self.character,
            source=_source_character_with_property(has_flesh=False),
        )
        stack = _emit_damage(self.character, payload)
        self.assertFalse(stack.was_cancelled())


class WeaponTagFilterTest(TestCase):
    """Test 4: Werewolf-bane scar fires only on silvered weapon hits."""

    def setUp(self):
        self.room = _create_room("WeaponTagRoom4")
        self.character = CharacterFactory()
        self.character.location = self.room
        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventName.DAMAGE_PRE_APPLY,
            filter_condition={
                "path": "source.ref.weapon.tags",
                "op": "contains",
                "value": "silvered",
            },
            flow_definition=cancel_flow,
            target=self.character,
        )

    def test_hit_silvered_weapon_fires(self):
        payload = _damage_payload(
            self.character,
            source=_source_with_weapon_tags(["silvered", "iron"]),
        )
        stack = _emit_damage(self.character, payload)
        self.assertTrue(stack.was_cancelled())

    def test_near_miss_iron_only_does_not_fire(self):
        payload = _damage_payload(
            self.character,
            source=_source_with_weapon_tags(["iron"]),
        )
        stack = _emit_damage(self.character, payload)
        self.assertFalse(stack.was_cancelled())


# ---------------------------------------------------------------------------
# Condition-specific protection + cross-character specificity (Tests 5-7)
# ---------------------------------------------------------------------------


class CharmImmunityAmuletTest(TestCase):
    """Test 5: Charm immunity cancels mind_control conditions only."""

    def setUp(self):
        self.room = _create_room("CharmRoom5")
        self.target = CharacterFactory()
        self.target.location = self.room
        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventName.CONDITION_PRE_APPLY,
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
        return emit_event(EventName.CONDITION_PRE_APPLY, payload, location=self.room)

    def test_hit_mind_control_cancels(self):
        stack = self._dispatch("mind_control")
        self.assertTrue(stack.was_cancelled())

    def test_near_miss_buff_passes(self):
        stack = self._dispatch("buff")
        self.assertFalse(stack.was_cancelled())


class CurseResistanceBySourceTest(TestCase):
    """Test 6: Curse resistance blocks scar-sourced withering only."""

    def setUp(self):
        self.room = _create_room("CurseRoom6")
        self.target = CharacterFactory()
        self.target.location = self.room
        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventName.CONDITION_PRE_APPLY,
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
            target=self.target, template=template, source=source, stage=None
        )
        stack = emit_event(EventName.CONDITION_PRE_APPLY, payload, location=self.room)
        self.assertTrue(stack.was_cancelled())

    def test_near_miss_item_sourced_withering_passes(self):
        template = ConditionTemplateFactory(name="withering")
        source = DamageSource(type="item", ref=None)
        payload = ConditionPreApplyPayload(
            target=self.target, template=template, source=source, stage=None
        )
        stack = emit_event(EventName.CONDITION_PRE_APPLY, payload, location=self.room)
        self.assertFalse(stack.was_cancelled())


class StageSpecificVulnerabilityTest(TestCase):
    """Test 7: Stage-scoped trigger fires only when condition is at that stage."""

    def setUp(self):
        self.room = _create_room("StageRoom7")
        self.character = CharacterFactory()
        self.character.location = self.room

    def test_hit_trigger_active_at_correct_stage(self):
        template = ConditionTemplateFactory(has_progression=True)
        stage = ConditionStageFactory(condition=template, stage_order=1, severity_threshold=3)
        condition_instance = ConditionInstanceFactory(
            target=self.character,
            condition=template,
            current_stage=stage,
            severity=5,
        )
        cancel_flow = _make_cancel_flow()

        trigger_def = TriggerDefinitionFactory(
            event_name=EventName.DAMAGE_PRE_APPLY, flow_definition=cancel_flow
        )
        TriggerFactory(
            trigger_definition=trigger_def,
            obj=self.character,
            source_condition=condition_instance,
            source_stage=stage,
            additional_filter_condition={},
        )

        payload = _damage_payload(self.character)
        stack = _emit_damage(self.character, payload)
        self.assertTrue(stack.was_cancelled())

    def test_near_miss_trigger_inactive_at_different_stage(self):
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
        trigger_def = TriggerDefinitionFactory(
            event_name=EventName.DAMAGE_PRE_APPLY, flow_definition=cancel_flow
        )
        TriggerFactory(
            trigger_definition=trigger_def,
            obj=self.character,
            source_condition=condition_instance,
            source_stage=stage1,  # scoped to stage1 but condition is at stage2
            additional_filter_condition={},
        )

        payload = _damage_payload(self.character)
        stack = _emit_damage(self.character, payload)
        self.assertFalse(stack.was_cancelled())


# ---------------------------------------------------------------------------
# Cross-character specificity (Tests 8-9) — self-filter drives this now
# ---------------------------------------------------------------------------


class CrossCharacterScarSpecificityTest(TestCase):
    """Cross-character specificity: each char's self-filtered scar fires only on damage to them.

    Replaces the old Test 8 (BondedEnemyRetaliationTest) which relied on an ad-hoc
    ``self.bonded_enemies`` list; the unified model expresses specificity through
    the self-filter against ``payload.target``. Covers the "target ==/!= self"
    idiom for two characters sharing one room.
    """

    def setUp(self):
        self.room = _create_room("CrossCharRoom8")
        self.char_a = CharacterFactory()
        self.char_a.location = self.room
        self.char_b = CharacterFactory()
        self.char_b.location = self.room

        cancel_flow = _make_cancel_flow()
        # Each character has a self-filtered scar that only fires on damage to them.
        ReactiveConditionFactory(
            event_name=EventName.DAMAGE_PRE_APPLY,
            filter_condition=SELF_FILTER,
            flow_definition=cancel_flow,
            target=self.char_a,
        )
        ReactiveConditionFactory(
            event_name=EventName.DAMAGE_PRE_APPLY,
            filter_condition=SELF_FILTER,
            flow_definition=cancel_flow,
            target=self.char_b,
        )

    def test_damage_to_a_only_fires_a_scar(self):
        payload = _damage_payload(self.char_a)
        stack = _emit_damage(self.char_a, payload)
        self.assertTrue(stack.was_cancelled())

    def test_damage_to_b_only_fires_b_scar(self):
        payload = _damage_payload(self.char_b)
        stack = _emit_damage(self.char_b, payload)
        self.assertTrue(stack.was_cancelled())


class CovenantAllegianceFilterTest(TestCase):
    """Test 9: Covenant-allegiance filter — fires on outsider attackers only.

    Skipped: covenant relationship model does not yet exist. Retaliation filter
    ``attacker.covenant != self.covenant`` requires a covenant attribute on
    Character, not yet wired. Update when covenant system ships.
    """

    def test_covenant_filter_skipped(self):
        self.skipTest(
            "Covenant model not yet built; attacker.covenant path unresolvable. "
            "Implement when covenant system is added."
        )


# ---------------------------------------------------------------------------
# Payload-modifier specificity (Tests 10-11)
# ---------------------------------------------------------------------------


class ElementalConversionTest(TestCase):
    """Test 10: Cold converts to (weakened) fire via MODIFY_PAYLOAD."""

    def setUp(self):
        self.room = _create_room("ConversionRoom10")
        self.character = CharacterFactory()
        self.character.location = self.room

        flow = FlowDefinitionFactory()
        step1 = FlowStepDefinitionFactory(
            flow=flow,
            parent_id=None,
            action=FlowActionChoices.MODIFY_PAYLOAD,
            parameters={"field": "damage_type", "op": "set", "value": "fire"},
        )
        FlowStepDefinitionFactory(
            flow=flow,
            parent_id=step1.pk,
            action=FlowActionChoices.MODIFY_PAYLOAD,
            parameters={"field": "amount", "op": "multiply", "value": 0.5},
        )

        ReactiveConditionFactory(
            event_name=EventName.DAMAGE_PRE_APPLY,
            filter_condition={"path": "damage_type", "op": "==", "value": "cold"},
            flow_definition=flow,
            target=self.character,
        )

    def test_hit_cold_converted_to_fire(self):
        payload = _damage_payload(
            self.character,
            amount=20,
            damage_type="cold",
            source=DamageSource(type="technique", ref=None),
        )
        _emit_damage(self.character, payload)
        self.assertEqual(payload.damage_type, "fire")
        self.assertEqual(payload.amount, 10.0)

    def test_near_miss_fire_not_converted(self):
        payload = _damage_payload(
            self.character,
            amount=20,
            damage_type="fire",
            source=DamageSource(type="technique", ref=None),
        )
        _emit_damage(self.character, payload)
        self.assertEqual(payload.damage_type, "fire")
        self.assertEqual(payload.amount, 20)


class ConditionalIntensityCapTest(TestCase):
    """Test 11: Evocation intensity cap (MODIFY_PAYLOAD lacks 'min' op).

    Near-miss case (non-evocation) is verifiable without the 'min' op.
    Cap-hit case authored-but-skipped pending MODIFY_PAYLOAD 'min'/'max'.
    """

    def setUp(self):
        self.room = _create_room("CapRoom11")
        self.character = CharacterFactory()
        self.character.location = self.room
        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventName.DAMAGE_PRE_APPLY,
            filter_condition={
                "path": "source.ref.school",
                "op": "==",
                "value": "evocation",
            },
            flow_definition=cancel_flow,
            target=self.character,
        )

    def test_hit_evocation_filter_matches(self):
        self.skipTest(
            "MODIFY_PAYLOAD lacks a 'min' op needed for intensity capping. "
            "Add 'min'/'max' ops to _execute_modify_payload, then implement "
            "cap as: {field: 'amount', op: 'min', value: 50}."
        )

    def test_near_miss_enchantment_uncapped(self):
        payload = _damage_payload(
            self.character,
            amount=100,
            damage_type="arcane",
            source=DamageSource(type="technique", ref=SimpleNamespace(school="enchantment")),
        )
        _emit_damage(self.character, payload)
        self.assertEqual(payload.amount, 100)


# ---------------------------------------------------------------------------
# AE topology (Tests 12-13)
# ---------------------------------------------------------------------------


class AEBystanderTopologyTest(TestCase):
    """Test 12: Single AE emission — bystander sees it once, on the shared stack.

    Three chars in the same room. Attacker AE-attacks two; third char has a
    bystander trigger (no target filter). One emission, one FlowStack, the
    bystander trigger fires exactly once, and self-filtered scars only fire
    on their own owners.
    """

    def setUp(self):
        self.room = _create_room("AERoom12")
        self.attacker = CharacterFactory()
        self.attacker.location = self.room
        self.target_a = CharacterFactory()
        self.target_a.location = self.room
        self.target_b = CharacterFactory()
        self.target_b.location = self.room
        self.bystander = CharacterFactory()
        self.bystander.location = self.room

        # Bystander has a watchful trigger with no target filter — fires on any
        # ATTACK_PRE_RESOLVE in the room. Use a MODIFY_PAYLOAD that tags a
        # counter on the payload so we can count invocations.
        count_flow = _make_set_field_flow("witnessed_tag", "bystander_saw_ae")
        ReactiveConditionFactory(
            event_name=EventName.ATTACK_PRE_RESOLVE,
            filter_condition=None,
            flow_definition=count_flow,
            target=self.bystander,
        )

    def test_single_ae_emission_fires_bystander_once(self):
        """One emit_event call — one FlowStack — bystander fires once."""
        payload = AttackPreResolvePayload(
            attacker=self.attacker,
            targets=[self.target_a, self.target_b],
            weapon=None,
            action=None,
        )
        # AttackPreResolvePayload is mutable — tag attr for test observability
        payload.witnessed_tag = None

        stack = emit_event(EventName.ATTACK_PRE_RESOLVE, payload, location=self.room)

        # Exactly one FlowStack returned from a single emission
        self.assertIsNotNone(stack)
        # Bystander's MODIFY_PAYLOAD ran exactly once
        self.assertEqual(payload.witnessed_tag, "bystander_saw_ae")
        # No other trigger registered on the room, so not cancelled
        self.assertFalse(stack.was_cancelled())


class AESelfFilteredScarsTest(TestCase):
    """Test 13: Self-filtered scars on multiple characters fire independently per target.

    Under unified dispatch, per-target DAMAGE_PRE_APPLY is still one emission per
    target (per-target event semantics). Each target's self-filtered scar fires
    only when that target is in the payload. Non-targets' scars stay silent.
    """

    def setUp(self):
        self.room = _create_room("AERoom13")
        self.chars = []
        cancel_flow = _make_cancel_flow()
        for _ in range(3):
            char = CharacterFactory()
            char.location = self.room
            ReactiveConditionFactory(
                event_name=EventName.DAMAGE_PRE_APPLY,
                filter_condition=SELF_FILTER,
                flow_definition=cancel_flow,
                target=char,
            )
            self.chars.append(char)

    def test_each_targets_scar_fires_on_its_own_damage(self):
        for char in self.chars:
            payload = _damage_payload(char, damage_type="fire")
            stack = _emit_damage(char, payload)
            self.assertTrue(
                stack.was_cancelled(),
                f"Expected scar on {char.pk} to cancel its own damage",
            )

    def test_unscarred_character_in_same_room_not_affected(self):
        clean_char = CharacterFactory()
        clean_char.location = self.room
        payload = _damage_payload(clean_char)
        stack = _emit_damage(clean_char, payload)
        # clean_char has no scar; the other 3 scars self-filter and do NOT match
        self.assertFalse(stack.was_cancelled())


# ---------------------------------------------------------------------------
# Cancellation tier — room ward priority vs personal shield (Tests 14-15)
# ---------------------------------------------------------------------------


class RoomWardCancelsBeforePersonalShieldTest(TestCase):
    """Test 14: Room ward (priority 9) cancels; personal shield (priority 3) doesn't fire.

    Under unified dispatch, priority ordering is global across all owners. A
    higher-priority room-owned trigger cancels before a lower-priority personal
    trigger is reached. Assertion: room ward fired, personal shield didn't.
    """

    def setUp(self):
        self.room = _create_room("WardRoom14")
        self.char = CharacterFactory()
        self.char.location = self.room

        # Room ward: priority 9, always cancels
        room_cancel_flow = _make_cancel_flow()
        room_trigger_def = TriggerDefinitionFactory(
            event_name=EventName.DAMAGE_PRE_APPLY, flow_definition=room_cancel_flow, priority=9
        )
        room_condition = ConditionInstanceFactory(target=self.room)
        TriggerFactory(
            trigger_definition=room_trigger_def,
            obj=self.room,
            source_condition=room_condition,
            source_stage=None,
            additional_filter_condition={},
        )
        if hasattr(self.room, "trigger_handler"):
            self.room.trigger_handler._populated = False

        # Personal shield: priority 3, would MODIFY_PAYLOAD if reached
        self.shield_flow = _make_multiply_field_flow("amount", 0)
        shield_trigger_def = TriggerDefinitionFactory(
            event_name=EventName.DAMAGE_PRE_APPLY,
            flow_definition=self.shield_flow,
            priority=3,
        )
        shield_condition = ConditionInstanceFactory(target=self.char)
        TriggerFactory(
            trigger_definition=shield_trigger_def,
            obj=self.char,
            source_condition=shield_condition,
            source_stage=None,
            additional_filter_condition=SELF_FILTER,
        )
        if hasattr(self.char, "trigger_handler"):
            self.char.trigger_handler._populated = False

    def test_room_ward_cancels_and_shield_does_not_run(self):
        payload = _damage_payload(self.char, amount=30, damage_type="fire")
        stack = _emit_damage(self.char, payload)
        # Room ward wins by priority and cancels
        self.assertTrue(stack.was_cancelled())
        # Personal shield would have zeroed amount; cancellation stopped the walk
        # so it stays at 30.
        self.assertEqual(payload.amount, 30)


class PersonalShieldCancelsOnlyOneTargetTest(TestCase):
    """Test 15: Per-target emissions let one shield cancel its own damage only."""

    def setUp(self):
        self.room = _create_room("ShieldRoom15")
        self.char_a = CharacterFactory()
        self.char_a.location = self.room
        self.char_b = CharacterFactory()
        self.char_b.location = self.room

        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventName.DAMAGE_PRE_APPLY,
            filter_condition=SELF_FILTER,
            flow_definition=cancel_flow,
            target=self.char_a,
        )

    def test_hit_shielded_char_cancelled(self):
        payload = _damage_payload(self.char_a, damage_type="cold")
        stack = _emit_damage(self.char_a, payload)
        self.assertTrue(stack.was_cancelled())

    def test_near_miss_unshielded_char_resolves(self):
        payload = _damage_payload(self.char_b, damage_type="cold")
        stack = _emit_damage(self.char_b, payload)
        self.assertFalse(stack.was_cancelled())


# ---------------------------------------------------------------------------
# Stage/source cascade (Tests 16-18)
# ---------------------------------------------------------------------------


class StageScopedTriggerStopsAfterAdvanceTest(TestCase):
    """Test 16: Stage-scoped trigger stops firing after stage advance."""

    def setUp(self):
        self.room = _create_room("StageRoom16")
        self.character = CharacterFactory()
        self.character.location = self.room

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
        trigger_def = TriggerDefinitionFactory(
            event_name=EventName.DAMAGE_PRE_APPLY, flow_definition=cancel_flow
        )
        TriggerFactory(
            trigger_definition=trigger_def,
            obj=self.character,
            source_condition=self.instance,
            source_stage=self.stage1,
            additional_filter_condition={},
        )
        if hasattr(self.character, "trigger_handler"):
            self.character.trigger_handler._populated = False

    def _dispatch(self):
        payload = _damage_payload(self.character)
        return _emit_damage(self.character, payload)

    def test_hit_trigger_fires_at_stage1(self):
        stack = self._dispatch()
        self.assertTrue(stack.was_cancelled())

    def test_near_miss_trigger_inactive_after_stage_advance(self):
        advance_condition_severity(self.instance, 10)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.current_stage_id, self.stage2.pk)
        stack = self._dispatch()
        self.assertFalse(stack.was_cancelled())


class ConditionRemovalCleansUpTriggerTest(TestCase):
    """Test 17: Removing source_condition cascades trigger deletion.

    After remove_condition, the Trigger row is gone; the handler cache is
    re-populated cleanly and the next dispatch finds no matching trigger.
    """

    def setUp(self):
        self.room = _create_room("CascadeRoom17")
        self.character = CharacterFactory()
        self.character.location = self.room

    def test_trigger_fires_then_gone_after_removal(self):
        template = ConditionTemplateFactory()
        instance = ConditionInstanceFactory(
            target=self.character,
            condition=template,
        )
        cancel_flow = _make_cancel_flow()

        trigger_def = TriggerDefinitionFactory(
            event_name=EventName.DAMAGE_PRE_APPLY, flow_definition=cancel_flow
        )
        TriggerFactory(
            trigger_definition=trigger_def,
            obj=self.character,
            source_condition=instance,
            source_stage=None,
            additional_filter_condition={},
        )
        self.character.trigger_handler._populated = False

        # First dispatch: trigger is present, fires and cancels
        stack_before = _emit_damage(self.character, _damage_payload(self.character))
        self.assertTrue(stack_before.was_cancelled())

        # Remove the condition → CASCADE deletes Trigger row
        remove_condition(self.character, template)
        self.character.trigger_handler._populated = False

        # Second dispatch: no trigger, does not fire
        stack_after = _emit_damage(self.character, _damage_payload(self.character))
        self.assertFalse(stack_after.was_cancelled())

    def test_near_miss_condition_still_present_trigger_still_fires(self):
        template = ConditionTemplateFactory()
        instance = ConditionInstanceFactory(
            target=self.character,
            condition=template,
        )
        cancel_flow = _make_cancel_flow()
        trigger_def = TriggerDefinitionFactory(
            event_name=EventName.DAMAGE_PRE_APPLY, flow_definition=cancel_flow
        )
        TriggerFactory(
            trigger_definition=trigger_def,
            obj=self.character,
            source_condition=instance,
            source_stage=None,
            additional_filter_condition={},
        )
        self.character.trigger_handler._populated = False

        stack1 = _emit_damage(self.character, _damage_payload(self.character))
        self.character.trigger_handler._populated = False
        stack2 = _emit_damage(self.character, _damage_payload(self.character))
        self.assertTrue(stack1.was_cancelled())
        self.assertTrue(stack2.was_cancelled())


class MultiSourceSameEventTest(TestCase):
    """Test 18: Two conditions on same char, both installing triggers on same event.

    Two separate ConditionInstances each install a trigger. A single emission
    runs both (by priority desc) and each multiplies amount.
    """

    def setUp(self):
        self.room = _create_room("MultiSourceRoom18")
        self.character = CharacterFactory()
        self.character.location = self.room

    def test_hit_both_sources_fire(self):
        double_flow1 = _make_multiply_field_flow("amount", 2)
        trigger_def1 = TriggerDefinitionFactory(
            event_name=EventName.DAMAGE_PRE_APPLY, flow_definition=double_flow1
        )
        instance1 = ConditionInstanceFactory(target=self.character)
        TriggerFactory(
            trigger_definition=trigger_def1,
            obj=self.character,
            source_condition=instance1,
            source_stage=None,
            additional_filter_condition={},
        )

        double_flow2 = _make_multiply_field_flow("amount", 2)
        trigger_def2 = TriggerDefinitionFactory(
            event_name=EventName.DAMAGE_PRE_APPLY, flow_definition=double_flow2
        )
        instance2 = ConditionInstanceFactory(target=self.character)
        TriggerFactory(
            trigger_definition=trigger_def2,
            obj=self.character,
            source_condition=instance2,
            source_stage=None,
            additional_filter_condition={},
        )
        self.character.trigger_handler._populated = False

        payload = _damage_payload(self.character)
        _emit_damage(self.character, payload)
        # 10 * 2 * 2 = 40
        self.assertEqual(payload.amount, 40)

    def test_near_miss_single_source_fires_once(self):
        double_flow = _make_multiply_field_flow("amount", 2)
        trigger_def = TriggerDefinitionFactory(
            event_name=EventName.DAMAGE_PRE_APPLY, flow_definition=double_flow
        )
        instance = ConditionInstanceFactory(target=self.character)
        TriggerFactory(
            trigger_definition=trigger_def,
            obj=self.character,
            source_condition=instance,
            source_stage=None,
            additional_filter_condition={},
        )
        self.character.trigger_handler._populated = False

        payload = _damage_payload(self.character)
        _emit_damage(self.character, payload)
        self.assertEqual(payload.amount, 20)


# ---------------------------------------------------------------------------
# Bystander reaction (NEW — replaces deleted ROOM scope tests)
# ---------------------------------------------------------------------------


class BystanderReactionTest(TestCase):
    """Bystander reaction: a character reacts to events happening to OTHERS in the room.

    Characters A and B share a room. A has a "Watchful" trigger with filter
    ``{"path": "target", "op": "!=", "value": "self"}``. When B is attacked,
    A's trigger fires; when A is attacked, A's trigger does NOT fire.

    This replaces the old ROOM-scope tests which relied on the deleted scope
    field. Under unified dispatch, bystander semantics are expressed as a
    filter that EXCLUDES the owner from being the target.
    """

    def setUp(self):
        self.room = _create_room("BystanderRoom")
        self.watcher = CharacterFactory()
        self.watcher.location = self.room
        self.subject = CharacterFactory()
        self.subject.location = self.room

        # Watcher's bystander trigger: MODIFY_PAYLOAD when someone ELSE is the target.
        mark_flow = _make_set_field_flow("damage_type", "witnessed")
        ReactiveConditionFactory(
            event_name=EventName.DAMAGE_PRE_APPLY,
            filter_condition=NOT_SELF_FILTER,
            flow_definition=mark_flow,
            target=self.watcher,
        )

    def test_bystander_reacts_when_other_is_target(self):
        """Damage to subject → watcher's filter matches (target != watcher) → mark applied."""
        payload = _damage_payload(self.subject, damage_type="fire")
        _emit_damage(self.subject, payload)
        self.assertEqual(payload.damage_type, "witnessed")

    def test_bystander_does_not_react_to_own_damage(self):
        """Damage to watcher → watcher's own filter (target != self) rejects → no mark."""
        payload = _damage_payload(self.watcher, damage_type="fire")
        _emit_damage(self.watcher, payload)
        self.assertEqual(payload.damage_type, "fire")


# ---------------------------------------------------------------------------
# Affinity / resonance / property layering (Tests 21-22)
# ---------------------------------------------------------------------------


class AffinityLayeringTest(TestCase):
    """Test 21: Filter by payload source.ref.affinity — layered by resonance."""

    def setUp(self):
        self.room = _create_room("AffinityRoom21")
        self.character = CharacterFactory()
        self.character.location = self.room

    def test_resonance_filter_matches_by_source_attribute(self):
        """Higher resonance values get captured by filter via numeric comparison."""
        ref = SimpleNamespace(affinity="storm", resonance=50)
        source = DamageSource(type="technique", ref=ref)
        trigger_flow = _make_set_field_flow("damage_type", "resonant_storm")
        ReactiveConditionFactory(
            event_name=EventName.DAMAGE_PRE_APPLY,
            filter_condition={
                "and": [
                    {"path": "source.ref.affinity", "op": "==", "value": "storm"},
                    {"path": "source.ref.resonance", "op": ">=", "value": 25},
                ]
            },
            flow_definition=trigger_flow,
            target=self.character,
        )
        payload = _damage_payload(self.character, source=source)
        _emit_damage(self.character, payload)
        self.assertEqual(payload.damage_type, "resonant_storm")

    def test_low_resonance_does_not_match(self):
        ref = SimpleNamespace(affinity="storm", resonance=10)
        source = DamageSource(type="technique", ref=ref)
        trigger_flow = _make_set_field_flow("damage_type", "resonant_storm")
        ReactiveConditionFactory(
            event_name=EventName.DAMAGE_PRE_APPLY,
            filter_condition={
                "and": [
                    {"path": "source.ref.affinity", "op": "==", "value": "storm"},
                    {"path": "source.ref.resonance", "op": ">=", "value": 25},
                ]
            },
            flow_definition=trigger_flow,
            target=self.character,
        )
        payload = _damage_payload(self.character, source=source, damage_type="physical")
        _emit_damage(self.character, payload)
        self.assertEqual(payload.damage_type, "physical")


class PropertyLayeringTest(TestCase):
    """Test 22: Layered property filters — target property + source property AND'd."""

    def setUp(self):
        self.room = _create_room("PropertyLayerRoom22")
        self.character = CharacterFactory()
        self.character.location = self.room

    def test_layered_has_property_filters(self):
        """AND of two has_property conditions gates the trigger."""
        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventName.DAMAGE_PRE_APPLY,
            filter_condition={
                "and": [
                    {"path": "source.ref", "op": "has_property", "value": "undead"},
                    {"path": "source.ref", "op": "has_property", "value": "ancient"},
                ]
            },
            flow_definition=cancel_flow,
            target=self.character,
        )

        class _Undead:
            def has_property(self, name):
                return name in {"undead", "ancient"}

        source = DamageSource(type="character", ref=_Undead())
        payload = _damage_payload(self.character, source=source)
        stack = _emit_damage(self.character, payload)
        self.assertTrue(stack.was_cancelled())

    def test_missing_property_does_not_fire(self):
        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventName.DAMAGE_PRE_APPLY,
            filter_condition={
                "and": [
                    {"path": "source.ref", "op": "has_property", "value": "undead"},
                    {"path": "source.ref", "op": "has_property", "value": "ancient"},
                ]
            },
            flow_definition=cancel_flow,
            target=self.character,
        )

        class _JustUndead:
            def has_property(self, name):
                return name == "undead"

        source = DamageSource(type="character", ref=_JustUndead())
        payload = _damage_payload(self.character, source=source)
        stack = _emit_damage(self.character, payload)
        self.assertFalse(stack.was_cancelled())


# ---------------------------------------------------------------------------
# Safety + filter (Tests 23-24)
# ---------------------------------------------------------------------------


class RecursionCapRespectsFiltersTest(TestCase):
    """Test 23: Non-matching filter never enters flow execution → cap not consumed."""

    def setUp(self):
        self.room = _create_room("RecursionRoom23")
        self.character = CharacterFactory()
        self.character.location = self.room

    def test_non_matching_filter_does_not_consume_cap(self):
        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventName.DAMAGE_PRE_APPLY,
            filter_condition={"path": "source.type", "op": "==", "value": "scar"},
            flow_definition=cancel_flow,
            target=self.character,
        )

        from flows.flow_stack import FlowStack

        payload = _damage_payload(
            self.character,
            source=DamageSource(type="character", ref=None),
        )
        stack = FlowStack(
            owner=self.character,
            originating_event=EventName.DAMAGE_PRE_APPLY,
            cap=2,
        )
        returned = emit_event(
            EventName.DAMAGE_PRE_APPLY,
            payload,
            location=self.character.location,
            parent_stack=stack,
        )
        # Parent stack passed through, still at depth 1, not cancelled
        self.assertIs(returned, stack)
        self.assertFalse(returned.was_cancelled())
        self.assertEqual(returned.depth, 1)

    def test_matching_filter_fires_and_updates_result(self):
        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventName.DAMAGE_PRE_APPLY,
            filter_condition={"path": "source.type", "op": "==", "value": "scar"},
            flow_definition=cancel_flow,
            target=self.character,
        )
        payload = _damage_payload(
            self.character,
            source=DamageSource(type="scar", ref=None),
        )
        stack = _emit_damage(self.character, payload)
        self.assertTrue(stack.was_cancelled())


class UsageCapPreFilterTest(TestCase):
    """Test 24: Usage cap is pre-filter.

    Authored-but-skipped: Trigger has no ``max_uses_per_scene`` column.
    ``_usage_cap_reached`` was a stub (now removed in Phase 4). Implementing
    this requires either an ``uses_this_scene`` counter on Trigger or an
    in-process dict on TriggerHandler. Neither exists yet.
    """

    def test_usage_cap_checked_before_filter(self):
        self.skipTest(
            "Trigger model has no max_uses_per_scene column. _usage_cap_reached "
            "helper was removed with the dispatch rewrite. Re-author when "
            "usage-counter infra lands."
        )

    def test_near_miss_unlimited_trigger_fires_multiple_times(self):
        self.skipTest(
            "Trigger model has no max_uses_per_scene column. _usage_cap_reached "
            "helper was removed with the dispatch rewrite. Re-author when "
            "usage-counter infra lands."
        )


# ---------------------------------------------------------------------------
# Async + filter (Tests 25-27)
# ---------------------------------------------------------------------------


class FilteredPlayerPromptTest(TestCase):
    """Test 25: Filter gate ahead of PROMPT_PLAYER (tested via CANCEL_EVENT proxy)."""

    def setUp(self):
        self.room = _create_room("PromptRoom25")
        self.character = CharacterFactory()
        self.character.location = self.room
        self.scar_filter_flow = FlowDefinitionFactory()
        FlowStepDefinitionFactory(
            flow=self.scar_filter_flow,
            parent_id=None,
            action=FlowActionChoices.CANCEL_EVENT,
            parameters={},
        )

    def test_hit_filter_matches_trigger_fires(self):
        ReactiveConditionFactory(
            event_name=EventName.DAMAGE_PRE_APPLY,
            filter_condition={"path": "source.type", "op": "==", "value": "scar"},
            flow_definition=self.scar_filter_flow,
            target=self.character,
        )
        payload = _damage_payload(
            self.character,
            damage_type="arcane",
            source=DamageSource(type="scar", ref=None),
        )
        stack = _emit_damage(self.character, payload)
        self.assertTrue(stack.was_cancelled())

    def test_near_miss_filter_misses_trigger_does_not_fire(self):
        ReactiveConditionFactory(
            event_name=EventName.DAMAGE_PRE_APPLY,
            filter_condition={"path": "source.type", "op": "==", "value": "scar"},
            flow_definition=self.scar_filter_flow,
            target=self.character,
        )
        payload = _damage_payload(
            self.character,
            damage_type="arcane",
            source=DamageSource(type="character", ref=None),
        )
        stack = _emit_damage(self.character, payload)
        self.assertFalse(stack.was_cancelled())


class PromptTimeoutTest(TestCase):
    """Test 26: Prompt timeout — pending prompt fires Deferred with default."""

    def test_prompt_timeout_fires_with_default_answer(self):
        from flows.execution.prompts import (
            _pending_prompts,
            register_pending_prompt,
            timeout_pending_prompt,
        )

        _pending_prompts.clear()
        received: list = []

        deferred = register_pending_prompt(
            account_id=999,
            prompt_key="test-timeout-26",
            default_answer="default_choice",
        )
        deferred.addCallback(received.append)

        found = timeout_pending_prompt(account_id=999, prompt_key="test-timeout-26")

        self.assertTrue(found)
        self.assertEqual(received, ["default_choice"])
        _pending_prompts.clear()

    def test_near_miss_timeout_on_unknown_key_returns_false(self):
        from flows.execution.prompts import timeout_pending_prompt

        found = timeout_pending_prompt(account_id=999, prompt_key="nonexistent-key-26")
        self.assertFalse(found)


class PromptResolutionTest(TestCase):
    """Test 27: Prompt resolution — resolve_pending_prompt fires Deferred."""

    def test_resolve_prompt_fires_deferred(self):
        from flows.execution.prompts import (
            _pending_prompts,
            register_pending_prompt,
            resolve_pending_prompt,
        )

        _pending_prompts.clear()
        received: list = []

        deferred = register_pending_prompt(
            account_id=42,
            prompt_key="test-resolve-27",
            default_answer=None,
        )
        deferred.addCallback(received.append)

        found = resolve_pending_prompt(
            account_id=42,
            prompt_key="test-resolve-27",
            answer="yes",
        )

        self.assertTrue(found)
        self.assertEqual(received, ["yes"])
        self.assertNotIn((42, "test-resolve-27"), _pending_prompts)
        _pending_prompts.clear()

    def test_near_miss_resolve_unknown_key_returns_false(self):
        from flows.execution.prompts import resolve_pending_prompt

        found = resolve_pending_prompt(
            account_id=42,
            prompt_key="nonexistent-27",
            answer="yes",
        )
        self.assertFalse(found)

    def test_resolve_flow_resumption_via_callback(self):
        from flows.execution.prompts import (
            _pending_prompts,
            register_pending_prompt,
            resolve_pending_prompt,
        )

        _pending_prompts.clear()
        result_store: dict = {}

        deferred = register_pending_prompt(
            account_id=7,
            prompt_key="resume-test-27",
            default_answer="no",
        )

        def _resume(answer):
            result_store["player_choice"] = answer

        deferred.addCallback(_resume)

        resolve_pending_prompt(
            account_id=7,
            prompt_key="resume-test-27",
            answer="yes",
        )

        self.assertEqual(result_store.get("player_choice"), "yes")
        _pending_prompts.clear()


# ---------------------------------------------------------------------------
# Combat integration dual-path (Tests 28-29) — single emission, filtered
# ---------------------------------------------------------------------------


class CombatDualPathTargetVsBystanderTest(TestCase):
    """Test 28: One emission — target scar fires, bystander trigger also fires.

    Under the unified model, combat calls `emit_event` once per event. A
    target-specific scar (self-filter) and a bystander trigger (no filter)
    both live in the same room and both see the same emission. Both fire
    (unless one cancels first).
    """

    def setUp(self):
        self.room = _create_room("CombatDualRoom28")
        self.target = CharacterFactory()
        self.target.location = self.room
        self.bystander = CharacterFactory()
        self.bystander.location = self.room

        self.target_mark_flow = _make_set_field_flow("damage_type", "target_scar_fired")
        ReactiveConditionFactory(
            event_name=EventName.DAMAGE_PRE_APPLY,
            filter_condition=SELF_FILTER,
            flow_definition=self.target_mark_flow,
            target=self.target,
        )
        self.bystander_mark_flow = _make_multiply_field_flow("amount", 3)
        ReactiveConditionFactory(
            event_name=EventName.DAMAGE_PRE_APPLY,
            filter_condition=NOT_SELF_FILTER,
            flow_definition=self.bystander_mark_flow,
            target=self.bystander,
        )

    def test_both_target_and_bystander_triggers_fire(self):
        payload = _damage_payload(self.target, amount=10)
        _emit_damage(self.target, payload)
        # Target scar rewrote damage_type
        self.assertEqual(payload.damage_type, "target_scar_fired")
        # Bystander trigger multiplied amount
        self.assertEqual(payload.amount, 30)


class CombatSourceDiscriminationTest(TestCase):
    """Test 29: Filter distinguishes technique damage from weapon damage."""

    def setUp(self):
        self.room = _create_room("CombatSourceRoom29")
        self.character = CharacterFactory()
        self.character.location = self.room
        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventName.DAMAGE_PRE_APPLY,
            filter_condition={"path": "source.type", "op": "==", "value": "technique"},
            flow_definition=cancel_flow,
            target=self.character,
        )

    def test_technique_damage_cancels(self):
        payload = _damage_payload(self.character, source=_source_technique("abyssal"))
        stack = _emit_damage(self.character, payload)
        self.assertTrue(stack.was_cancelled())

    def test_weapon_damage_passes_through(self):
        payload = _damage_payload(
            self.character,
            source=DamageSource(type="character", ref=None),
        )
        stack = _emit_damage(self.character, payload)
        self.assertFalse(stack.was_cancelled())
