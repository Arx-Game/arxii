"""Tests for the force-field/reflect/blink reactive effect bundles (#1584, Task 14b).

SQLite-safe: no ``apply_condition`` / ``bulk_apply_conditions`` (PG-only DISTINCT ON),
no ``@tag("postgres")``. Tests inspect seeded rows directly and exercise
``init_absorb_buffer`` against a factory-built ConditionInstance stub.

The full DAMAGE_PRE_APPLY → handler path is the Task 16 PG reactive E2E.
"""

from types import SimpleNamespace

from django.test import TestCase

from flows.constants import EventName
from flows.consts import FlowActionChoices
from flows.models.flows import FlowStepDefinition
from world.conditions.constants import (
    BLINK_CONDITION_NAME,
    FORCE_FIELD_CONDITION_NAME,
    REFLECT_CONDITION_NAME,
)
from world.conditions.factories import ConditionInstanceFactory
from world.conditions.models import ConditionTemplate
from world.magic.effect_palette_content import (
    BLINK_TECHNIQUE_NAME,
    FORCE_FIELD_TECHNIQUE_NAME,
    REFLECT_TECHNIQUE_NAME,
    ensure_blink_content,
    ensure_force_field_content,
    ensure_reflect_content,
)
from world.magic.models.techniques import (
    ConditionTargetKind,
    Technique,
    TechniqueAppliedCondition,
)
from world.magic.services.effect_handlers import init_absorb_buffer

_SELF_FILTER = {"path": "target", "op": "==", "value": "self"}


# ---------------------------------------------------------------------------
# Force-field (Aegis Field) bundle
# ---------------------------------------------------------------------------


class EnsureForceFieldContentTests(TestCase):
    """ensure_force_field_content() seeds the bundle and is idempotent."""

    def setUp(self) -> None:
        ensure_force_field_content()
        ensure_force_field_content()  # second call must not create duplicates

    def test_exactly_one_technique(self) -> None:
        self.assertEqual(Technique.objects.filter(name=FORCE_FIELD_TECHNIQUE_NAME).count(), 1)

    def test_exactly_one_condition_template(self) -> None:
        self.assertEqual(
            ConditionTemplate.objects.filter(name=FORCE_FIELD_CONDITION_NAME).count(), 1
        )

    def test_damage_pre_apply_trigger_wired_with_priority_10(self) -> None:
        template = ConditionTemplate.objects.get(name=FORCE_FIELD_CONDITION_NAME)
        triggers = list(template.reactive_triggers.filter(event_name=EventName.DAMAGE_PRE_APPLY))
        self.assertEqual(len(triggers), 1)
        t = triggers[0]
        self.assertEqual(t.priority, 10)
        self.assertEqual(t.base_filter_condition, _SELF_FILTER)

    def test_force_field_flow_has_no_cancel_event_step(self) -> None:
        template = ConditionTemplate.objects.get(name=FORCE_FIELD_CONDITION_NAME)
        dpa_trigger = template.reactive_triggers.get(event_name=EventName.DAMAGE_PRE_APPLY)
        cancel_steps = FlowStepDefinition.objects.filter(
            flow=dpa_trigger.flow_definition,
            action=FlowActionChoices.CANCEL_EVENT,
        )
        self.assertEqual(cancel_steps.count(), 0, "Force-field must NOT have a CANCEL_EVENT step")

    def test_force_field_flow_has_absorb_pool_call(self) -> None:
        template = ConditionTemplate.objects.get(name=FORCE_FIELD_CONDITION_NAME)
        dpa_trigger = template.reactive_triggers.get(event_name=EventName.DAMAGE_PRE_APPLY)
        steps = FlowStepDefinition.objects.filter(
            flow=dpa_trigger.flow_definition,
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
        )
        self.assertEqual(steps.count(), 1)
        self.assertIn("absorb_pool", steps.get().variable_name)

    def test_condition_applied_trigger_also_wired(self) -> None:
        """Force-field also has a CONDITION_APPLIED trigger for absorb-buffer init."""
        template = ConditionTemplate.objects.get(name=FORCE_FIELD_CONDITION_NAME)
        ca_triggers = list(
            template.reactive_triggers.filter(event_name=EventName.CONDITION_APPLIED)
        )
        self.assertEqual(len(ca_triggers), 1, "Aegis Field must have a CONDITION_APPLIED trigger")

    def test_condition_applied_flow_has_init_absorb_buffer_call(self) -> None:
        template = ConditionTemplate.objects.get(name=FORCE_FIELD_CONDITION_NAME)
        ca_trigger = template.reactive_triggers.get(event_name=EventName.CONDITION_APPLIED)
        steps = FlowStepDefinition.objects.filter(
            flow=ca_trigger.flow_definition,
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
        )
        self.assertEqual(steps.count(), 1)
        step = steps.get()
        self.assertIn("init_absorb_buffer", step.variable_name)
        self.assertEqual(step.parameters.get("payload"), "@payload")
        self.assertIn("buffer", step.parameters)

    def test_technique_applies_condition_to_self(self) -> None:
        technique = Technique.objects.get(name=FORCE_FIELD_TECHNIQUE_NAME)
        template = ConditionTemplate.objects.get(name=FORCE_FIELD_CONDITION_NAME)
        applied = TechniqueAppliedCondition.objects.filter(
            technique=technique,
            condition=template,
        )
        self.assertEqual(applied.count(), 1)
        self.assertEqual(applied.get().target_kind, ConditionTargetKind.SELF)


# ---------------------------------------------------------------------------
# Reflect (Mirror Ward) bundle
# ---------------------------------------------------------------------------


class EnsureReflectContentTests(TestCase):
    """ensure_reflect_content() seeds the bundle and is idempotent."""

    def setUp(self) -> None:
        ensure_reflect_content()
        ensure_reflect_content()  # idempotent

    def test_exactly_one_technique(self) -> None:
        self.assertEqual(Technique.objects.filter(name=REFLECT_TECHNIQUE_NAME).count(), 1)

    def test_exactly_one_condition_template(self) -> None:
        self.assertEqual(ConditionTemplate.objects.filter(name=REFLECT_CONDITION_NAME).count(), 1)

    def test_damage_pre_apply_trigger_wired_with_priority_20(self) -> None:
        template = ConditionTemplate.objects.get(name=REFLECT_CONDITION_NAME)
        triggers = list(template.reactive_triggers.filter(event_name=EventName.DAMAGE_PRE_APPLY))
        self.assertEqual(len(triggers), 1)
        t = triggers[0]
        self.assertEqual(t.priority, 20)
        self.assertEqual(t.base_filter_condition, _SELF_FILTER)

    def test_reflect_flow_has_cancel_event_child_step(self) -> None:
        template = ConditionTemplate.objects.get(name=REFLECT_CONDITION_NAME)
        dpa_trigger = template.reactive_triggers.get(event_name=EventName.DAMAGE_PRE_APPLY)
        cancel_steps = FlowStepDefinition.objects.filter(
            flow=dpa_trigger.flow_definition,
            action=FlowActionChoices.CANCEL_EVENT,
        )
        self.assertEqual(cancel_steps.count(), 1, "Reflect MUST have a CANCEL_EVENT step")
        cancel_step = cancel_steps.get()
        # Confirm it is a child of the CALL_SERVICE_FUNCTION root step
        self.assertIsNotNone(cancel_step.parent_id, "CANCEL_EVENT step must have a parent")
        self.assertEqual(cancel_step.parent.action, FlowActionChoices.CALL_SERVICE_FUNCTION)

    def test_reflect_flow_has_reflect_damage_call(self) -> None:
        template = ConditionTemplate.objects.get(name=REFLECT_CONDITION_NAME)
        dpa_trigger = template.reactive_triggers.get(event_name=EventName.DAMAGE_PRE_APPLY)
        steps = FlowStepDefinition.objects.filter(
            flow=dpa_trigger.flow_definition,
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
        )
        self.assertEqual(steps.count(), 1)
        self.assertIn("reflect_damage", steps.get().variable_name)

    def test_no_condition_applied_trigger(self) -> None:
        """Reflect has no CONDITION_APPLIED trigger — no buffer to init."""
        template = ConditionTemplate.objects.get(name=REFLECT_CONDITION_NAME)
        ca_triggers = template.reactive_triggers.filter(event_name=EventName.CONDITION_APPLIED)
        self.assertEqual(ca_triggers.count(), 0)

    def test_technique_applies_condition_to_self(self) -> None:
        technique = Technique.objects.get(name=REFLECT_TECHNIQUE_NAME)
        template = ConditionTemplate.objects.get(name=REFLECT_CONDITION_NAME)
        applied = TechniqueAppliedCondition.objects.filter(
            technique=technique,
            condition=template,
        )
        self.assertEqual(applied.count(), 1)
        self.assertEqual(applied.get().target_kind, ConditionTargetKind.SELF)


# ---------------------------------------------------------------------------
# Blink (Phase Step) bundle
# ---------------------------------------------------------------------------


class EnsureBlinkContentTests(TestCase):
    """ensure_blink_content() seeds the bundle and is idempotent."""

    def setUp(self) -> None:
        ensure_blink_content()
        ensure_blink_content()  # idempotent

    def test_exactly_one_technique(self) -> None:
        self.assertEqual(Technique.objects.filter(name=BLINK_TECHNIQUE_NAME).count(), 1)

    def test_exactly_one_condition_template(self) -> None:
        self.assertEqual(ConditionTemplate.objects.filter(name=BLINK_CONDITION_NAME).count(), 1)

    def test_damage_pre_apply_trigger_wired_with_priority_30(self) -> None:
        template = ConditionTemplate.objects.get(name=BLINK_CONDITION_NAME)
        triggers = list(template.reactive_triggers.filter(event_name=EventName.DAMAGE_PRE_APPLY))
        self.assertEqual(len(triggers), 1)
        t = triggers[0]
        self.assertEqual(t.priority, 30)
        self.assertEqual(t.base_filter_condition, _SELF_FILTER)

    def test_blink_flow_has_cancel_event_child_step(self) -> None:
        template = ConditionTemplate.objects.get(name=BLINK_CONDITION_NAME)
        dpa_trigger = template.reactive_triggers.get(event_name=EventName.DAMAGE_PRE_APPLY)
        cancel_steps = FlowStepDefinition.objects.filter(
            flow=dpa_trigger.flow_definition,
            action=FlowActionChoices.CANCEL_EVENT,
        )
        self.assertEqual(cancel_steps.count(), 1, "Blink MUST have a CANCEL_EVENT step")
        cancel_step = cancel_steps.get()
        # Confirm it is a child of the CALL_SERVICE_FUNCTION root step
        self.assertIsNotNone(cancel_step.parent_id, "CANCEL_EVENT step must have a parent")
        self.assertEqual(cancel_step.parent.action, FlowActionChoices.CALL_SERVICE_FUNCTION)

    def test_blink_flow_has_blink_dodge_call(self) -> None:
        template = ConditionTemplate.objects.get(name=BLINK_CONDITION_NAME)
        dpa_trigger = template.reactive_triggers.get(event_name=EventName.DAMAGE_PRE_APPLY)
        steps = FlowStepDefinition.objects.filter(
            flow=dpa_trigger.flow_definition,
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
        )
        self.assertEqual(steps.count(), 1)
        self.assertIn("blink_dodge", steps.get().variable_name)

    def test_no_condition_applied_trigger(self) -> None:
        """Blink has no CONDITION_APPLIED trigger — no buffer to init."""
        template = ConditionTemplate.objects.get(name=BLINK_CONDITION_NAME)
        ca_triggers = template.reactive_triggers.filter(event_name=EventName.CONDITION_APPLIED)
        self.assertEqual(ca_triggers.count(), 0)

    def test_technique_applies_condition_to_self(self) -> None:
        technique = Technique.objects.get(name=BLINK_TECHNIQUE_NAME)
        template = ConditionTemplate.objects.get(name=BLINK_CONDITION_NAME)
        applied = TechniqueAppliedCondition.objects.filter(
            technique=technique,
            condition=template,
        )
        self.assertEqual(applied.count(), 1)
        self.assertEqual(applied.get().target_kind, ConditionTargetKind.SELF)


# ---------------------------------------------------------------------------
# init_absorb_buffer unit tests
# ---------------------------------------------------------------------------


class InitAbsorbBufferTests(TestCase):
    """init_absorb_buffer seeds the force-field instance's absorb buffer on CONDITION_APPLIED."""

    def test_sets_absorb_remaining_when_null(self) -> None:
        """When absorb_remaining is None, it is set to buffer and saved."""
        inst = ConditionInstanceFactory(absorb_remaining=None)
        payload = SimpleNamespace(instance=inst)
        init_absorb_buffer(payload=payload, buffer=20)
        inst.refresh_from_db()
        self.assertEqual(inst.absorb_remaining, 20)

    def test_does_not_overwrite_existing_buffer(self) -> None:
        """When absorb_remaining already has a value, it is left unchanged."""
        inst = ConditionInstanceFactory(absorb_remaining=15)
        payload = SimpleNamespace(instance=inst)
        init_absorb_buffer(payload=payload, buffer=20)
        inst.refresh_from_db()
        self.assertEqual(inst.absorb_remaining, 15)

    def test_noop_when_instance_is_none(self) -> None:
        """When payload.instance is None, the function completes without error."""
        payload = SimpleNamespace(instance=None)
        init_absorb_buffer(payload=payload, buffer=20)  # must not raise
