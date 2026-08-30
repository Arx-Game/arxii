"""Crafting reward loop: appraisal + masterwork→renown (#2243)."""

from decimal import Decimal

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.items.crafting.reward import award_crafting_fame, crafting_deed_value, is_masterwork
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


class CraftingFameTests(TestCase):
    """Fame at first making (#2878): generalizes the #2243 masterwork threshold."""

    def test_is_masterwork_by_stat_multiplier(self):
        fine = QualityTierFactory(name="Fine", stat_multiplier=Decimal("1.5"))
        superb = QualityTierFactory(name="Superb", stat_multiplier=Decimal("2.0"))
        plain = QualityTierFactory(name="Plain", stat_multiplier=Decimal("1.0"))
        self.assertTrue(is_masterwork(fine))
        self.assertTrue(is_masterwork(superb))
        self.assertFalse(is_masterwork(plain))
        self.assertFalse(is_masterwork(None))

    def test_baseline_work_is_worth_no_fame(self):
        plain = QualityTierFactory(name="Plain", stat_multiplier=Decimal("1.0"))
        self.assertEqual(crafting_deed_value(plain), 0)

    def test_fame_scales_with_quality_and_accents(self):
        from types import SimpleNamespace

        superb = QualityTierFactory(name="Superb", stat_multiplier=Decimal("2.0"))
        bare = crafting_deed_value(superb)
        accented = crafting_deed_value(superb, [SimpleNamespace(level=SimpleNamespace(level=4))])
        self.assertGreater(bare, 0)
        self.assertGreater(accented, bare)

    def test_safe_work_mints_no_deed_however_fine(self):
        """#3463: an ordinary masterwork risks nothing, so it mints no Legend.

        Replaces two tests that both now assert this — one checked baseline work
        minted nothing (still true, and now true for every quality), the other
        checked a Superb piece credited both maker and designer with a deed each.
        That dual-credit path is not gone, it is gated: it fires when a working
        genuinely endangered its makers, which reaches Legend through the stakes
        settlement seam. Testing it today would mean patching
        _working_was_perilous to True and asserting a path no production caller
        reaches, which is worth less than the line it costs.

        crafting_deed_value keeps its own coverage above — it is the sizing
        function a perilous working will use, so it stays honest either way.
        """
        maker_sheet = CharacterSheetFactory()
        designer_sheet = CharacterSheetFactory()
        superb = QualityTierFactory(name="Superb", stat_multiplier=Decimal("2.0"))
        instance = ItemInstanceFactory()

        before = LegendEntry.objects.count()
        award_crafting_fame(
            crafter_persona=maker_sheet.primary_persona,
            designer_persona=designer_sheet.primary_persona,
            tier=superb,
            item_label="Blade",
            item_instance=instance,
        )

        self.assertEqual(LegendEntry.objects.count(), before)
        self.assertEqual(instance.legend_deeds.count(), 0)
