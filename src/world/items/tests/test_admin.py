"""Tests for items admin registrations (#3430: enchantment authoring inlines)."""

from django.contrib import admin
from django.test import TestCase

from world.items.admin import ItemCheckModifierInline, ItemTemplatePropertyInline
from world.items.models import ItemCheckModifier, ItemTemplate, ItemTemplateProperty


class ItemTemplateAdminInlineTests(TestCase):
    """ItemCheckModifier and ItemTemplateProperty authoring was shell-only (#3430
    gap): both are now TabularInlines on ItemTemplateAdmin."""

    def test_item_template_is_registered(self) -> None:
        assert ItemTemplate in admin.site._registry

    def test_check_modifier_inline_registered_on_item_template(self) -> None:
        model_admin = admin.site._registry[ItemTemplate]
        inline_models = [inline.model for inline in model_admin.inlines]
        assert ItemCheckModifier in inline_models

    def test_template_property_inline_registered_on_item_template(self) -> None:
        model_admin = admin.site._registry[ItemTemplate]
        inline_models = [inline.model for inline in model_admin.inlines]
        assert ItemTemplateProperty in inline_models

    def test_check_modifier_inline_is_tabular(self) -> None:
        assert issubclass(ItemCheckModifierInline, admin.TabularInline)

    def test_template_property_inline_is_tabular(self) -> None:
        assert issubclass(ItemTemplatePropertyInline, admin.TabularInline)

    def test_requires_attunement_in_a_fieldset(self) -> None:
        model_admin = admin.site._registry[ItemTemplate]
        all_fields = {field for _, opts in model_admin.fieldsets for field in opts["fields"]}
        assert "requires_attunement" in all_fields
