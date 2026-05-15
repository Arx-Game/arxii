"""Tests for ConditionTemplate.reactive_triggers M2M field."""

from django.test import TestCase

from flows.factories import TriggerDefinitionFactory
from world.conditions.factories import ConditionTemplateFactory


class ConditionTemplateReactiveTriggersFieldTests(TestCase):
    def test_can_attach_trigger_definitions_via_m2m(self):
        template = ConditionTemplateFactory()
        trigger_def = TriggerDefinitionFactory()
        template.reactive_triggers.add(trigger_def)
        self.assertIn(trigger_def, template.reactive_triggers.all())

    def test_m2m_is_empty_by_default(self):
        template = ConditionTemplateFactory()
        self.assertEqual(template.reactive_triggers.count(), 0)

    def test_related_name_installing_templates(self):
        template = ConditionTemplateFactory()
        trigger_def = TriggerDefinitionFactory()
        template.reactive_triggers.add(trigger_def)
        # Reverse access from TriggerDefinition to ConditionTemplate
        self.assertIn(template, trigger_def.installing_templates.all())
