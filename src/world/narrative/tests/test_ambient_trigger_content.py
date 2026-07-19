"""ensure_ambient_reaction_content() idempotent bootstrap (#2471)."""

from __future__ import annotations

from django.test import TestCase

from flows.constants import EventName
from flows.consts import FlowActionChoices
from flows.models import FlowDefinition, FlowStepDefinition
from flows.models.triggers import TriggerDefinition
from world.narrative.ambient_trigger_content import (
    AMBIENT_REACTION_FLOW_NAME,
    AMBIENT_REACTION_TRIGGER_NAME,
    ensure_ambient_reaction_content,
)


class EnsureAmbientReactionContentTests(TestCase):
    def test_creates_flow_and_trigger_definition(self) -> None:
        trigger_def = ensure_ambient_reaction_content()

        self.assertEqual(trigger_def.name, AMBIENT_REACTION_TRIGGER_NAME)
        self.assertEqual(trigger_def.event_name, EventName.MOVED)
        flow = FlowDefinition.objects.get(name=AMBIENT_REACTION_FLOW_NAME)
        self.assertEqual(trigger_def.flow_definition_id, flow.pk)
        step = FlowStepDefinition.objects.get(flow=flow)
        self.assertEqual(step.action, FlowActionChoices.CALL_SERVICE_FUNCTION)
        self.assertEqual(step.variable_name, "world.narrative.services.emit_room_ambient_reaction")
        self.assertEqual(step.parameters, {"payload": "@payload"})

    def test_idempotent(self) -> None:
        ensure_ambient_reaction_content()
        ensure_ambient_reaction_content()

        self.assertEqual(
            TriggerDefinition.objects.filter(name=AMBIENT_REACTION_TRIGGER_NAME).count(), 1
        )
        self.assertEqual(FlowDefinition.objects.filter(name=AMBIENT_REACTION_FLOW_NAME).count(), 1)
        self.assertEqual(
            FlowStepDefinition.objects.filter(flow__name=AMBIENT_REACTION_FLOW_NAME).count(),
            1,
        )
