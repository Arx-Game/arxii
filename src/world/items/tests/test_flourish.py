"""Tests for item flourish fields and resolution helper (#2023)."""

from django.test import TestCase

from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.services.flourish import resolve_item_flourish


class ResolveItemFlourishTests(TestCase):
    """Tests for resolve_item_flourish — template-vs-instance override precedence."""

    def test_returns_none_when_no_flourish_authored(self):
        """No flourish on template or instance -> None."""
        template = ItemTemplateFactory(flourish_text="")
        instance = ItemInstanceFactory(template=template, custom_flourish_text="")
        assert resolve_item_flourish(instance) is None

    def test_returns_template_flourish_when_no_override(self):
        """Template flourish present, no instance override -> template flourish."""
        template = ItemTemplateFactory(flourish_text="gleaming in the torchlight")
        instance = ItemInstanceFactory(template=template, custom_flourish_text="")
        assert resolve_item_flourish(instance) == "gleaming in the torchlight"

    def test_instance_override_takes_precedence(self):
        """Both set -> instance flourish wins."""
        template = ItemTemplateFactory(flourish_text="template flourish")
        instance = ItemInstanceFactory(template=template, custom_flourish_text="custom flourish")
        assert resolve_item_flourish(instance) == "custom flourish"

    def test_empty_instance_override_falls_back_to_template(self):
        """Empty string instance override -> falls back to template."""
        template = ItemTemplateFactory(flourish_text="template flourish")
        instance = ItemInstanceFactory(template=template, custom_flourish_text="")
        assert resolve_item_flourish(instance) == "template flourish"
