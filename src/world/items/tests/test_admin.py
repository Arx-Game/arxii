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


class ItemInstanceAdminMeaningTests(TestCase):
    """The item admin shows dedication, lineage and the computed meaning rail (#4512)."""

    @classmethod
    def setUpTestData(cls) -> None:
        from django.urls import reverse

        from evennia_extensions.factories import AccountFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.items.factories import ItemInstanceFactory, meaningful_item_for
        from world.items.models import ItemLineage

        cls.staff = AccountFactory(is_staff=True, is_superuser=True)
        cls.holder = CharacterSheetFactory()
        cls.item = meaningful_item_for(cls.holder, designer_character_sheet=cls.holder)
        ItemLineage.objects.create(item=cls.item, source_item=None, source_name="saddle", points=4)
        cls.url = reverse("admin:arxii_iteminstance_change", args=(cls.item.pk,))
        cls.nobody = ItemInstanceFactory()

    def test_the_rail_lists_the_signals_and_the_page_carries_its_rules(self) -> None:
        self.client.force_login(self.staff)

        body = self.client.get(self.url).content.decode()

        assert "Meaning for the current holder" in body
        assert "Designed by you" in body
        # The rail's own rules reach the page, and so does the stock form stylesheet.
        assert "item-meaning-rail" in body
        assert ".item-meaning-cols" in body
        assert "admin/css/forms.css" in body
        assert "Dedication (read-only)" in body
        assert "Points at consumption" in body

    def test_the_help_this_slice_added_names_no_issue_or_function(self) -> None:
        import re

        self.client.force_login(self.staff)

        body = self.client.get(self.url).content.decode()
        helps = re.findall(r'<div class="help"[^>]*>(.*?)</div>', body, re.DOTALL)

        assert helps
        assert not [h for h in helps if re.search(r"#4512|set_item_holder", h)]

    def test_an_item_nobody_holds_says_so(self) -> None:
        self.client.force_login(self.staff)
        from django.urls import reverse

        body = self.client.get(
            reverse("admin:arxii_iteminstance_change", args=(self.nobody.pk,))
        ).content.decode()

        assert "Nobody holds this item" in body
