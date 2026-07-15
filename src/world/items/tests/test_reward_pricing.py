"""Crafting reward loop: appraisal + masterwork→renown (#2243)."""

from decimal import Decimal

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.items.crafting.reward import award_masterwork_renown, is_masterwork
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory, QualityTierFactory
from world.items.services.pricing import appraise
from world.societies.models import LegendEntry


class AppraiseTests(TestCase):
    def test_value_scales_by_quality_and_adds_materials(self):
        tier = QualityTierFactory(name="Masterwork", stat_multiplier=Decimal("2.0"))
        template = ItemTemplateFactory(name="Blade", value=100)
        instance = ItemInstanceFactory(template=template, quality_tier=tier, lore_value=20)
        self.assertEqual(appraise(instance), 220)  # 100 * 2.0 + 20

    def test_shoddy_item_is_worth_its_base(self):
        tier = QualityTierFactory(name="Shoddy", stat_multiplier=Decimal("1.0"))
        template = ItemTemplateFactory(name="Rag", value=40)
        instance = ItemInstanceFactory(template=template, quality_tier=tier, lore_value=0)
        self.assertEqual(appraise(instance), 40)

    def test_no_quality_tier_falls_back_to_base_plus_materials(self):
        template = ItemTemplateFactory(name="Lump", value=30)
        instance = ItemInstanceFactory(template=template, quality_tier=None, lore_value=5)
        self.assertEqual(appraise(instance), 35)


class MasterworkRenownTests(TestCase):
    def test_is_masterwork_by_stat_multiplier(self):
        fine = QualityTierFactory(name="Fine", stat_multiplier=Decimal("1.5"))
        superb = QualityTierFactory(name="Superb", stat_multiplier=Decimal("2.0"))
        plain = QualityTierFactory(name="Plain", stat_multiplier=Decimal("1.0"))
        self.assertTrue(is_masterwork(fine))
        self.assertTrue(is_masterwork(superb))
        self.assertFalse(is_masterwork(plain))
        self.assertFalse(is_masterwork(None))

    def test_masterwork_grants_the_maker_a_legend_deed(self):
        sheet = CharacterSheetFactory()
        tier = QualityTierFactory(name="Superb", stat_multiplier=Decimal("2.0"))

        before = LegendEntry.objects.count()
        award_masterwork_renown(crafter_character_sheet=sheet, tier=tier, item_label="Blade")

        self.assertEqual(LegendEntry.objects.count(), before + 1)
        entry = LegendEntry.objects.latest("id")
        self.assertEqual(entry.persona, sheet.primary_persona)
        self.assertIn("masterwork", entry.title.lower())

    def test_masterwork_with_item_instance_links_deed(self):
        sheet = CharacterSheetFactory()
        tier = QualityTierFactory(name="Superb", stat_multiplier=Decimal("2.0"))
        instance = ItemInstanceFactory()

        award_masterwork_renown(
            crafter_character_sheet=sheet,
            tier=tier,
            item_label="Blade",
            item_instance=instance,
        )

        entry = LegendEntry.objects.latest("id")
        self.assertIn(entry, instance.legend_deeds.all())
        self.assertGreater(instance.legend_value, 0)

    def test_masterwork_without_item_instance_still_works(self):
        sheet = CharacterSheetFactory()
        tier = QualityTierFactory(name="Superb", stat_multiplier=Decimal("2.0"))

        before = LegendEntry.objects.count()
        award_masterwork_renown(crafter_character_sheet=sheet, tier=tier, item_label="Blade")

        self.assertEqual(LegendEntry.objects.count(), before + 1)
