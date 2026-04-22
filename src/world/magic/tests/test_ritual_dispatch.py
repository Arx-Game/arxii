"""Tests for PerformRitualAction — Spec A §4.3.

Covers:
- SERVICE dispatch (end-to-end via spend_resonance_for_imbuing)
- FLOW dispatch (patched execute_flow assertion)
- Component validation: missing, wrong template, insufficient quantity
- Component consumption: rows deleted after successful execute()
"""

import unittest.mock

from django.test import TestCase

from flows.factories import FlowDefinitionFactory
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import ItemInstance
from world.magic.actions import PerformRitualAction
from world.magic.constants import RitualExecutionKind
from world.magic.exceptions import RitualComponentError
from world.magic.factories import (
    CharacterSheetFactory,
    ImbuingRitualFactory,
    RitualComponentRequirementFactory,
    RitualFactory,
    ThreadFactory,
)
from world.magic.services import grant_resonance


class PerformRitualActionServiceTests(TestCase):
    """SERVICE-kind rituals dispatch to an imported Python function."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.actor = CharacterSheetFactory()
        # _trait_value=100 gives the trait anchor a cap of 100 so the thread
        # is not already at cap when we call imbuing with amount=50.
        cls.thread = ThreadFactory(owner=cls.actor, _trait_value=100)
        grant_resonance(cls.actor, cls.thread.resonance, 100, source="setup")
        cls.ritual = ImbuingRitualFactory()

    def test_imbuing_dispatches_to_spend_resonance_for_imbuing(self) -> None:
        """PerformRitualAction → spend_resonance_for_imbuing, result.resonance_spent == 50."""
        action = PerformRitualAction(
            actor=self.actor,
            ritual=self.ritual,
            components_provided=[],
            kwargs={"thread": self.thread, "amount": 50},
        )
        result = action.execute()
        self.assertEqual(result.resonance_spent, 50)

    def test_service_ritual_factory_shape(self) -> None:
        """ImbuingRitualFactory produces a SERVICE-kind Ritual with correct path."""
        self.assertEqual(self.ritual.execution_kind, RitualExecutionKind.SERVICE)
        self.assertEqual(
            self.ritual.service_function_path,
            "world.magic.services.spend_resonance_for_imbuing",
        )


class PerformRitualActionFlowTests(TestCase):
    """FLOW-kind rituals construct a FlowExecution and call stack.execute_flow."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.actor = CharacterSheetFactory()
        cls.flow = FlowDefinitionFactory()
        cls.ritual = RitualFactory(
            execution_kind=RitualExecutionKind.FLOW,
            flow=cls.flow,
            service_function_path="",
        )

    def test_flow_dispatch_executes_flow(self) -> None:
        """FLOW dispatch calls FlowStack.execute_flow with the correct FlowExecution."""
        with unittest.mock.patch("flows.flow_stack.FlowStack.execute_flow") as mock_execute:
            action = PerformRitualAction(
                actor=self.actor,
                ritual=self.ritual,
                components_provided=[],
                kwargs={},
            )
            result = action.execute()

        mock_execute.assert_called_once()
        execution_arg = mock_execute.call_args[0][0]
        self.assertEqual(execution_arg.flow_definition, self.flow)
        self.assertIsNone(result)

    def test_flow_dispatch_returns_none(self) -> None:
        """FLOW dispatch always returns None (result comes from the flow side-effects)."""
        with unittest.mock.patch("flows.flow_stack.FlowStack.execute_flow"):
            action = PerformRitualAction(
                actor=self.actor,
                ritual=self.ritual,
                components_provided=[],
                kwargs={},
            )
            result = action.execute()
        self.assertIsNone(result)


class PerformRitualActionComponentTests(TestCase):
    """Component validation and consumption behaviour."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.actor = CharacterSheetFactory()
        cls.template = ItemTemplateFactory()
        cls.ritual = RitualFactory()
        cls.req = RitualComponentRequirementFactory(
            ritual=cls.ritual,
            item_template=cls.template,
            quantity=1,
        )

    def test_missing_component_raises(self) -> None:
        """No components provided → RitualComponentError."""
        action = PerformRitualAction(
            actor=self.actor,
            ritual=self.ritual,
            components_provided=[],
            kwargs={},
        )
        with self.assertRaises(RitualComponentError):
            action.execute()

    def test_components_are_consumed(self) -> None:
        """ItemInstance rows that satisfy requirements are deleted after execute()."""
        inst = ItemInstanceFactory(template=self.template)
        action = PerformRitualAction(
            actor=self.actor,
            ritual=self.ritual,
            components_provided=[inst],
            kwargs={},
        )
        with unittest.mock.patch(
            "world.magic.actions.PerformRitualAction._dispatch_service",
            return_value=None,
        ):
            action.execute()

        self.assertFalse(ItemInstance.objects.filter(pk=inst.pk).exists())

    def test_wrong_template_raises(self) -> None:
        """ItemInstance with the wrong template does not satisfy the requirement."""
        other_template = ItemTemplateFactory()
        wrong_inst = ItemInstanceFactory(template=other_template)
        action = PerformRitualAction(
            actor=self.actor,
            ritual=self.ritual,
            components_provided=[wrong_inst],
            kwargs={},
        )
        with self.assertRaises(RitualComponentError):
            action.execute()

    def test_insufficient_quantity_raises(self) -> None:
        """One instance (qty=1) against a requirement of 3 → RitualComponentError."""
        ritual = RitualFactory()
        RitualComponentRequirementFactory(
            ritual=ritual,
            item_template=self.template,
            quantity=3,
        )
        inst = ItemInstanceFactory(template=self.template, quantity=1)
        action = PerformRitualAction(
            actor=self.actor,
            ritual=ritual,
            components_provided=[inst],
            kwargs={},
        )
        with self.assertRaises(RitualComponentError):
            action.execute()
