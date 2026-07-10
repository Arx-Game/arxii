"""Tests for the simple effect bundles + ensure_effect_palette_content() (#1584, Task 14c).

SQLite-safe: no ``apply_condition`` / ``bulk_apply_conditions`` (PG-only DISTINCT ON),
no ``@tag("postgres")``. Tests inspect seeded rows directly.

The full cast → CONDITION_APPLIED → trigger → handler paths are covered by the
Task 15/16 PG E2Es; this module's own tests stay SQLite-safe.
"""

from django.test import TestCase

from flows.constants import EventName
from flows.consts import FlowActionChoices
from flows.models.flows import FlowStepDefinition
from world.conditions.constants import (
    INCORPOREAL_CONDITION_NAME,
    OBSTACLE_CONDITION_NAME,
    SINK_CONDITION_NAME,
    TELEKINESIS_CONDITION_NAME,
    TELEPORT_CONDITION_NAME,
)
from world.conditions.models import ConditionTemplate
from world.magic.effect_palette_content import (
    BLINK_TECHNIQUE_NAME,
    FORCE_FIELD_TECHNIQUE_NAME,
    INCORPOREAL_TECHNIQUE_NAME,
    OBSTACLE_TECHNIQUE_NAME,
    REFLECT_TECHNIQUE_NAME,
    SINK_TECHNIQUE_NAME,
    SUMMON_TECHNIQUE_NAME,
    TELEKINESIS_TECHNIQUE_NAME,
    TELEPORT_TECHNIQUE_NAME,
    ensure_effect_palette_content,
    ensure_incorporeal_content,
    ensure_obstacle_content,
    ensure_sink_content,
    ensure_telekinesis_content,
    ensure_teleport_content,
)
from world.magic.models.techniques import (
    ConditionTargetKind,
    Technique,
    TechniqueAppliedCondition,
)

_SELF_FILTER = {"path": "target", "op": "==", "value": "self"}

# All nine technique names that ensure_effect_palette_content() must create.
_ALL_NINE_NAMES = [
    SUMMON_TECHNIQUE_NAME,  # 14a
    FORCE_FIELD_TECHNIQUE_NAME,  # 14b
    REFLECT_TECHNIQUE_NAME,  # 14b
    BLINK_TECHNIQUE_NAME,  # 14b
    TELEPORT_TECHNIQUE_NAME,  # 14c
    OBSTACLE_TECHNIQUE_NAME,  # 14c
    INCORPOREAL_TECHNIQUE_NAME,  # 14c
    SINK_TECHNIQUE_NAME,  # 14c
    TELEKINESIS_TECHNIQUE_NAME,  # 14c
]


# ---------------------------------------------------------------------------
# Teleport (Phase Jump) bundle
# ---------------------------------------------------------------------------


class EnsureTeleportContentTests(TestCase):
    """ensure_teleport_content() seeds the bundle and is idempotent."""

    def setUp(self) -> None:
        ensure_teleport_content()
        ensure_teleport_content()  # second call must not create duplicates

    def test_exactly_one_technique(self) -> None:
        self.assertEqual(Technique.objects.filter(name=TELEPORT_TECHNIQUE_NAME).count(), 1)

    def test_exactly_one_condition_template(self) -> None:
        self.assertEqual(ConditionTemplate.objects.filter(name=TELEPORT_CONDITION_NAME).count(), 1)

    def test_condition_applied_trigger_wired(self) -> None:
        template = ConditionTemplate.objects.get(name=TELEPORT_CONDITION_NAME)
        ca_triggers = list(
            template.reactive_triggers.filter(event_name=EventName.CONDITION_APPLIED)
        )
        self.assertEqual(len(ca_triggers), 1)
        t = ca_triggers[0]
        self.assertEqual(t.base_filter_condition, _SELF_FILTER)

    def test_flow_step_calls_move_position_adapter(self) -> None:
        template = ConditionTemplate.objects.get(name=TELEPORT_CONDITION_NAME)
        trigger = template.reactive_triggers.get(event_name=EventName.CONDITION_APPLIED)
        steps = FlowStepDefinition.objects.filter(
            flow=trigger.flow_definition,
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
        )
        self.assertEqual(steps.count(), 1)
        step = steps.get()
        self.assertIn("move_position_on_condition", step.variable_name)
        self.assertEqual(step.parameters.get("payload"), "@payload")
        self.assertIn("destination_position_id", step.parameters)

    def test_technique_applies_condition_to_self(self) -> None:
        technique = Technique.objects.get(name=TELEPORT_TECHNIQUE_NAME)
        template = ConditionTemplate.objects.get(name=TELEPORT_CONDITION_NAME)
        applied = TechniqueAppliedCondition.objects.filter(technique=technique, condition=template)
        self.assertEqual(applied.count(), 1)
        self.assertEqual(applied.get().target_kind, ConditionTargetKind.SELF)


# ---------------------------------------------------------------------------
# Obstacle (Barricade) bundle
# ---------------------------------------------------------------------------


class EnsureObstacleContentTests(TestCase):
    """ensure_obstacle_content() seeds the bundle and is idempotent."""

    def setUp(self) -> None:
        ensure_obstacle_content()
        ensure_obstacle_content()  # idempotent

    def test_exactly_one_technique(self) -> None:
        self.assertEqual(Technique.objects.filter(name=OBSTACLE_TECHNIQUE_NAME).count(), 1)

    def test_exactly_one_condition_template(self) -> None:
        self.assertEqual(ConditionTemplate.objects.filter(name=OBSTACLE_CONDITION_NAME).count(), 1)

    def test_condition_applied_trigger_wired(self) -> None:
        template = ConditionTemplate.objects.get(name=OBSTACLE_CONDITION_NAME)
        ca_triggers = list(
            template.reactive_triggers.filter(event_name=EventName.CONDITION_APPLIED)
        )
        self.assertEqual(len(ca_triggers), 1)
        t = ca_triggers[0]
        self.assertEqual(t.base_filter_condition, _SELF_FILTER)

    def test_flow_step_calls_create_obstacle_adapter(self) -> None:
        template = ConditionTemplate.objects.get(name=OBSTACLE_CONDITION_NAME)
        trigger = template.reactive_triggers.get(event_name=EventName.CONDITION_APPLIED)
        steps = FlowStepDefinition.objects.filter(
            flow=trigger.flow_definition,
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
        )
        self.assertEqual(steps.count(), 1)
        step = steps.get()
        self.assertIn("create_obstacle_on_condition", step.variable_name)
        self.assertEqual(step.parameters.get("payload"), "@payload")
        self.assertIn("position_a_id", step.parameters)
        self.assertIn("position_b_id", step.parameters)

    def test_technique_applies_condition_to_self(self) -> None:
        technique = Technique.objects.get(name=OBSTACLE_TECHNIQUE_NAME)
        template = ConditionTemplate.objects.get(name=OBSTACLE_CONDITION_NAME)
        applied = TechniqueAppliedCondition.objects.filter(technique=technique, condition=template)
        self.assertEqual(applied.count(), 1)
        self.assertEqual(applied.get().target_kind, ConditionTargetKind.SELF)


# ---------------------------------------------------------------------------
# Incorporeal (Ghostform) bundle — intangibility gate only
# ---------------------------------------------------------------------------


class EnsureIncorporealContentTests(TestCase):
    """ensure_incorporeal_content() seeds the bundle and is idempotent."""

    def setUp(self) -> None:
        ensure_incorporeal_content()
        ensure_incorporeal_content()  # idempotent

    def test_exactly_one_technique(self) -> None:
        self.assertEqual(Technique.objects.filter(name=INCORPOREAL_TECHNIQUE_NAME).count(), 1)

    def test_exactly_one_condition_template(self) -> None:
        self.assertEqual(
            ConditionTemplate.objects.filter(name=INCORPOREAL_CONDITION_NAME).count(), 1
        )

    def test_condition_category_grants_intangibility(self) -> None:
        template = ConditionTemplate.objects.get(name=INCORPOREAL_CONDITION_NAME)
        self.assertTrue(template.category.grants_intangibility)

    def test_no_reactive_triggers(self) -> None:
        """Incorporeal has no handler — the Task 8 gate does the work."""
        template = ConditionTemplate.objects.get(name=INCORPOREAL_CONDITION_NAME)
        self.assertEqual(template.reactive_triggers.count(), 0)

    def test_technique_applies_condition_to_self(self) -> None:
        technique = Technique.objects.get(name=INCORPOREAL_TECHNIQUE_NAME)
        template = ConditionTemplate.objects.get(name=INCORPOREAL_CONDITION_NAME)
        applied = TechniqueAppliedCondition.objects.filter(technique=technique, condition=template)
        self.assertEqual(applied.count(), 1)
        self.assertEqual(applied.get().target_kind, ConditionTargetKind.SELF)


# ---------------------------------------------------------------------------
# Sink into earth (Earthmeld) bundle — 1-round intangibility
# ---------------------------------------------------------------------------


class EnsureSinkContentTests(TestCase):
    """ensure_sink_content() seeds the bundle and is idempotent."""

    def setUp(self) -> None:
        ensure_sink_content()
        ensure_sink_content()  # idempotent

    def test_exactly_one_technique(self) -> None:
        self.assertEqual(Technique.objects.filter(name=SINK_TECHNIQUE_NAME).count(), 1)

    def test_exactly_one_condition_template(self) -> None:
        self.assertEqual(ConditionTemplate.objects.filter(name=SINK_CONDITION_NAME).count(), 1)

    def test_condition_category_grants_intangibility(self) -> None:
        template = ConditionTemplate.objects.get(name=SINK_CONDITION_NAME)
        self.assertTrue(template.category.grants_intangibility)

    def test_sink_duration_is_one_round(self) -> None:
        """Earthmeld lasts exactly 1 round — shorter than Ghostform."""
        template = ConditionTemplate.objects.get(name=SINK_CONDITION_NAME)
        from world.conditions.constants import DurationType

        self.assertEqual(template.default_duration_type, DurationType.ROUNDS)
        self.assertEqual(template.default_duration_value, 1)

    def test_no_reactive_triggers(self) -> None:
        template = ConditionTemplate.objects.get(name=SINK_CONDITION_NAME)
        self.assertEqual(template.reactive_triggers.count(), 0)

    def test_technique_applies_condition_to_self(self) -> None:
        technique = Technique.objects.get(name=SINK_TECHNIQUE_NAME)
        template = ConditionTemplate.objects.get(name=SINK_CONDITION_NAME)
        applied = TechniqueAppliedCondition.objects.filter(technique=technique, condition=template)
        self.assertEqual(applied.count(), 1)
        self.assertEqual(applied.get().target_kind, ConditionTargetKind.SELF)


# ---------------------------------------------------------------------------
# Telekinesis (Force Grip) bundle — reposition enemy
# ---------------------------------------------------------------------------


class EnsureTelekinesisContentTests(TestCase):
    """ensure_telekinesis_content() seeds the bundle and is idempotent."""

    def setUp(self) -> None:
        ensure_telekinesis_content()
        ensure_telekinesis_content()  # idempotent

    def test_exactly_one_technique(self) -> None:
        self.assertEqual(Technique.objects.filter(name=TELEKINESIS_TECHNIQUE_NAME).count(), 1)

    def test_exactly_one_condition_template(self) -> None:
        self.assertEqual(
            ConditionTemplate.objects.filter(name=TELEKINESIS_CONDITION_NAME).count(), 1
        )

    def test_condition_applied_trigger_wired(self) -> None:
        template = ConditionTemplate.objects.get(name=TELEKINESIS_CONDITION_NAME)
        ca_triggers = list(
            template.reactive_triggers.filter(event_name=EventName.CONDITION_APPLIED)
        )
        self.assertEqual(len(ca_triggers), 1)

    def test_flow_step_calls_move_position_adapter(self) -> None:
        template = ConditionTemplate.objects.get(name=TELEKINESIS_CONDITION_NAME)
        trigger = template.reactive_triggers.get(event_name=EventName.CONDITION_APPLIED)
        steps = FlowStepDefinition.objects.filter(
            flow=trigger.flow_definition,
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
        )
        self.assertEqual(steps.count(), 1)
        step = steps.get()
        self.assertIn("force_move_target_on_condition", step.variable_name)
        self.assertEqual(step.parameters.get("payload"), "@payload")
        self.assertIn("destination_position_id", step.parameters)

    def test_technique_applies_condition_to_enemy(self) -> None:
        """Force Grip applies to an ENEMY — the telekinesis target."""
        technique = Technique.objects.get(name=TELEKINESIS_TECHNIQUE_NAME)
        template = ConditionTemplate.objects.get(name=TELEKINESIS_CONDITION_NAME)
        applied = TechniqueAppliedCondition.objects.filter(technique=technique, condition=template)
        self.assertEqual(applied.count(), 1)
        self.assertEqual(applied.get().target_kind, ConditionTargetKind.ENEMY)


# ---------------------------------------------------------------------------
# ensure_effect_palette_content() — all nine effects, idempotent
# ---------------------------------------------------------------------------


class EnsureEffectPaletteContentTests(TestCase):
    """ensure_effect_palette_content() seeds all nine effects and is idempotent."""

    def test_seeds_all_nine_techniques_idempotently(self) -> None:
        """Double-call creates exactly nine techniques, zero duplicates."""
        ensure_effect_palette_content()
        ensure_effect_palette_content()  # second call must not create dupes

        matching = Technique.objects.filter(name__in=_ALL_NINE_NAMES)
        self.assertEqual(
            matching.count(),
            len(_ALL_NINE_NAMES),
            f"Expected {len(_ALL_NINE_NAMES)} techniques; got {matching.count()}. "
            f"Present: {list(matching.values_list('name', flat=True))}",
        )
