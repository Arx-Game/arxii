"""Event catering → host prestige (#2852). SQLite tier."""

from unittest.mock import patch

from django.test import TestCase

from world.events.constants import EventStatus
from world.events.models import EventHost
from world.events.services import (
    _award_catering_prestige,
    _catering_score,
    cater_event,
)
from world.events.types import EventError


class CaterEventTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        from world.events.factories import EventFactory

        cls.event = EventFactory(status=EventStatus.ACTIVE)

    def _consumable(self, holder_sheet, quality=None):
        from evennia import create_object

        from world.items.factories import ItemInstanceFactory, ItemTemplateFactory

        obj = create_object("typeclasses.objects.Object", key="dish", nohome=True)
        template = ItemTemplateFactory(is_consumable=True, max_charges=1)
        return ItemInstanceFactory(
            template=template,
            holder_character_sheet=holder_sheet,
            game_object=obj,
            quality_tier=quality,
        )

    def test_catering_consumes_the_instance_and_snapshots(self):
        from world.character_sheets.factories import CharacterSheetFactory
        from world.items.models import ItemInstance

        sheet = CharacterSheetFactory()
        instance = self._consumable(sheet)
        row = cater_event(self.event, sheet.character, instance)
        self.assertEqual(row.event, self.event)
        self.assertFalse(ItemInstance.objects.filter(pk=instance.pk).exists())

    def test_non_consumables_are_refused(self):
        from evennia import create_object

        from world.character_sheets.factories import CharacterSheetFactory
        from world.items.factories import ItemInstanceFactory, ItemTemplateFactory

        sheet = CharacterSheetFactory()
        obj = create_object("typeclasses.objects.Object", key="statue", nohome=True)
        instance = ItemInstanceFactory(
            template=ItemTemplateFactory(is_consumable=False),
            holder_character_sheet=sheet,
            game_object=obj,
        )
        with self.assertRaises(EventError):
            cater_event(self.event, sheet.character, instance)

    def test_score_sums_quality_multipliers(self):
        from world.character_sheets.factories import CharacterSheetFactory
        from world.items.factories import QualityTierFactory

        sheet = CharacterSheetFactory()
        fine = QualityTierFactory(name="Fine", stat_multiplier="1.25")
        master = QualityTierFactory(name="Masterwork", stat_multiplier="1.60")
        cater_event(self.event, sheet.character, self._consumable(sheet, quality=fine))
        cater_event(self.event, sheet.character, self._consumable(sheet, quality=master))
        cater_event(self.event, sheet.character, self._consumable(sheet))
        self.assertEqual(_catering_score(self.event), round(1.25 + 1.60 + 1.0))

    def test_completion_mints_the_host_hospitality_deed(self):
        from world.character_sheets.factories import CharacterSheetFactory
        from world.items.factories import QualityTierFactory

        sheet = CharacterSheetFactory()
        host_sheet = CharacterSheetFactory()
        host_persona = host_sheet.primary_persona
        EventHost.objects.create(event=self.event, persona=host_persona, is_primary=True)
        master = QualityTierFactory(name="Masterwork", stat_multiplier="1.60")
        cater_event(self.event, sheet.character, self._consumable(sheet, quality=master))
        cater_event(self.event, sheet.character, self._consumable(sheet, quality=master))
        with patch("world.societies.services.create_solo_deed") as deed:
            _award_catering_prestige(self.event)
        deed.assert_called_once()
        args = deed.call_args.args
        self.assertEqual(args[0], host_persona)
        self.assertIn("lavish table", args[1])

    def test_thin_spread_mints_nothing(self):
        from world.character_sheets.factories import CharacterSheetFactory

        sheet = CharacterSheetFactory()
        host_persona = CharacterSheetFactory().primary_persona
        EventHost.objects.create(event=self.event, persona=host_persona, is_primary=True)
        cater_event(self.event, sheet.character, self._consumable(sheet))
        with patch("world.societies.services.create_solo_deed") as deed:
            _award_catering_prestige(self.event)
        deed.assert_not_called()


class ProvisioningSeedTest(TestCase):
    def test_seed_creates_skill_check_tiers_and_recipes(self):
        from django.test import override_settings

        from world.items.crafting.models import CraftingRecipe, CraftingSkillCap
        from world.items.models import QualityTier

        with override_settings(SEED_SAMPLE_CONTENT=True):
            from world.seeds.provisioning_checks import seed_provisioning_content

            seed_provisioning_content()
        self.assertEqual(QualityTier.objects.count(), 3)
        cook_recipes = CraftingRecipe.objects.filter(name__startswith="Cook: ")
        refine_recipes = CraftingRecipe.objects.filter(name__startswith="Refine: ")
        self.assertEqual(cook_recipes.count(), 2)
        self.assertEqual(refine_recipes.count(), 2)
        for recipe in list(cook_recipes) + list(refine_recipes):
            self.assertFalse(recipe.requires_station)
            self.assertEqual(recipe.check_type.name, "Cooking")
            self.assertEqual(CraftingSkillCap.objects.filter(recipe=recipe).count(), 3)
            self.assertGreater(recipe.material_requirements.count(), 0)
        for recipe in cook_recipes:
            self.assertIsNone(recipe.required_feature_kind)
        for recipe in refine_recipes:
            self.assertEqual(recipe.required_feature_kind.name, "Workshop of Iniquity")
