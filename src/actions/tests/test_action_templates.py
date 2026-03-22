"""Tests for ActionTemplate and ActionTemplateGate models."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from actions.constants import GateRole, Pipeline
from actions.factories import (
    ActionTemplateFactory,
    ActionTemplateGateFactory,
)


class ActionTemplateModelTests(TestCase):
    """Test ActionTemplate model validation."""

    def test_creation(self) -> None:
        template = ActionTemplateFactory(name="Fire Bolt")
        assert template.name == "Fire Bolt"
        assert template.pipeline == Pipeline.SINGLE

    def test_str(self) -> None:
        template = ActionTemplateFactory(name="Fire Bolt")
        assert str(template) == "Fire Bolt"

    def test_single_pipeline_with_gate_rejected(self) -> None:
        template = ActionTemplateFactory(pipeline=Pipeline.SINGLE)
        ActionTemplateGateFactory(action_template=template)
        with self.assertRaises(ValidationError):
            template.full_clean()

    def test_gated_pipeline_without_gate_rejected(self) -> None:
        template = ActionTemplateFactory(pipeline=Pipeline.GATED)
        with self.assertRaises(ValidationError):
            template.full_clean()

    def test_gated_pipeline_with_gate_valid(self) -> None:
        template = ActionTemplateFactory(pipeline=Pipeline.GATED)
        ActionTemplateGateFactory(action_template=template)
        template.full_clean()  # Should not raise


class ActionTemplateGateModelTests(TestCase):
    """Test ActionTemplateGate model validation."""

    def test_creation(self) -> None:
        gate = ActionTemplateGateFactory()
        assert gate.gate_role == GateRole.ACTIVATION
        assert gate.failure_aborts is True

    def test_gate_without_consequence_pool(self) -> None:
        gate = ActionTemplateGateFactory(consequence_pool=None)
        assert gate.consequence_pool is None

    def test_str(self) -> None:
        template = ActionTemplateFactory(name="Fire Bolt", pipeline=Pipeline.GATED)
        gate = ActionTemplateGateFactory(action_template=template, gate_role=GateRole.ACTIVATION)
        assert "Fire Bolt" in str(gate)
        assert "Activation" in str(gate)

    def test_unique_constraint_role_per_template(self) -> None:
        template = ActionTemplateFactory(pipeline=Pipeline.GATED)
        ActionTemplateGateFactory(action_template=template, gate_role=GateRole.ACTIVATION)
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            ActionTemplateGateFactory(action_template=template, gate_role=GateRole.ACTIVATION)
