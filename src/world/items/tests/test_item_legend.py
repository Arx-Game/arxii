"""Tests for item legend value via M2M link to LegendEntry (#2359)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.items.factories import ItemInstanceFactory
from world.societies.factories import LegendEntryFactory, LegendSourceTypeFactory


class ItemLegendValueTests(TestCase):
    def test_legend_value_zero_with_no_linked_deeds(self):
        instance = ItemInstanceFactory()
        self.assertEqual(instance.legend_value, 0)

    def test_legend_value_sums_active_linked_deeds(self):
        instance = ItemInstanceFactory()
        source_type = LegendSourceTypeFactory()
        sheet = CharacterSheetFactory()
        deed1 = LegendEntryFactory(
            persona=sheet.primary_persona, source_type=source_type, base_value=50
        )
        deed2 = LegendEntryFactory(
            persona=sheet.primary_persona, source_type=source_type, base_value=30
        )
        instance.legend_deeds.add(deed1, deed2)
        self.assertEqual(instance.legend_value, 80)

    def test_legend_value_excludes_inactive_deeds(self):
        instance = ItemInstanceFactory()
        source_type = LegendSourceTypeFactory()
        sheet = CharacterSheetFactory()
        active = LegendEntryFactory(
            persona=sheet.primary_persona,
            source_type=source_type,
            base_value=50,
            is_active=True,
        )
        inactive = LegendEntryFactory(
            persona=sheet.primary_persona,
            source_type=source_type,
            base_value=100,
            is_active=False,
        )
        instance.legend_deeds.add(active, inactive)
        self.assertEqual(instance.legend_value, 50)
