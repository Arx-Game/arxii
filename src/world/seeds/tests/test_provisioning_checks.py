"""Cooking check-spine seed — wits+agility average + Cooking skill (+ Brewing) (#2852).

#3006 trimmed this module: the four example ITEM_CREATE recipes it used to mint
directly (Hearty Stew, Honeyed Wine, Dream Dust, Haze) — plus their ingredient
ItemTemplates and skill-cap ladders — moved to the lore repo, because
``CraftingRecipe``/``CraftingSkillCap``/``CraftingMaterialRequirement`` became
``CONTENT_MODELS`` (#3006 Task 1) and a seeder minting them directly now
violates the #2698 "seeders never write content" rule (see
``world.seeds.tests.test_no_content_slop``). The regression test below is the
one that would have caught the old shape.
"""

from django.test import TestCase, override_settings

from world.checks.models import CheckType, CheckTypeSpecialization, CheckTypeTrait
from world.items.models import AccentLevel, QualityTier
from world.seeds.checks import seed_check_resolution_tables
from world.seeds.provisioning_checks import COOKING_CHECK_NAME, seed_provisioning_content
from world.skills.models import Skill, Specialization
from world.traits.models import Trait, TraitType


@override_settings(SEED_SAMPLE_CONTENT=True)  # seed_provisioning_content gates on #2698
class ProvisioningCheckSeedTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        seed_check_resolution_tables()
        seed_provisioning_content()

    def test_seeds_cooking_skill(self) -> None:
        skill = Skill.objects.get(trait__name="Cooking")
        self.assertEqual(skill.trait.trait_type, TraitType.SKILL)

    def test_seeds_brewing_specialization_attached_to_check(self) -> None:
        check_type = CheckType.objects.get(name=COOKING_CHECK_NAME)
        specialization = Specialization.objects.get(name="Brewing")
        self.assertTrue(
            CheckTypeSpecialization.objects.filter(
                check_type=check_type, specialization=specialization
            ).exists()
        )

    def test_cooking_check_is_wits_agility_average_plus_cooking_skill(self) -> None:
        check_type = CheckType.objects.get(name=COOKING_CHECK_NAME)
        trait_names = set(
            CheckTypeTrait.objects.filter(check_type=check_type).values_list(
                "trait__name", flat=True
            )
        )
        self.assertEqual(trait_names, {"wits", "agility", "Cooking"})
        self.assertEqual(Trait.objects.get(name="Cooking").trait_type, TraitType.SKILL)

    def test_seeds_the_12_rung_quality_tier_ladder(self) -> None:
        self.assertEqual(QualityTier.objects.count(), 12)
        legendary = QualityTier.objects.get(name="Legendary")
        self.assertEqual(legendary.sort_order, 12)
        # The pre-#2878 3-row ladder is retired on seed.
        self.assertFalse(QualityTier.objects.filter(name__in=("Common", "Masterwork")).exists())

    def test_seeds_the_7_rung_accent_ladder(self) -> None:
        self.assertEqual(AccentLevel.objects.count(), 7)
        self.assertEqual(AccentLevel.objects.get(level=1).name, "slightly")

    def test_idempotent(self) -> None:
        seed_provisioning_content()
        seed_provisioning_content()
        check_type = CheckType.objects.get(name=COOKING_CHECK_NAME)
        # skill + wits + agility, no duplicates.
        self.assertEqual(CheckTypeTrait.objects.filter(check_type=check_type).count(), 3)
        self.assertEqual(QualityTier.objects.count(), 12)
        self.assertEqual(AccentLevel.objects.count(), 7)

    def test_does_not_mint_crafting_recipes_or_their_ingredients(self) -> None:
        """The post-#3006 contract: recipes are authored content, not seeder output.

        Before #3006 this seeder unconditionally minted the four example
        ITEM_CREATE recipes (plus ingredient ItemTemplates and skill caps) once
        the Cooking check resolved — which happens here under
        ``SEED_SAMPLE_CONTENT=True``. That directly wrote rows into
        ``CraftingRecipe``/``CraftingMaterialRequirement``/``CraftingSkillCap``,
        all three now ``CONTENT_MODELS`` (#3006 Task 1) — a seeder populating a
        ``CONTENT_MODELS`` table is exactly what ``test_no_content_slop`` guards
        against. This asserts the seeder stays silent on all of it.
        """
        from world.items.crafting.models import (
            CraftingMaterialRequirement,
            CraftingRecipe,
            CraftingSkillCap,
        )
        from world.items.models import ItemTemplate

        self.assertEqual(CraftingRecipe.objects.count(), 0)
        self.assertEqual(CraftingMaterialRequirement.objects.count(), 0)
        self.assertEqual(CraftingSkillCap.objects.count(), 0)
        dropped_ingredient_names = (
            "Sack of Grain",
            "Wild Herbs",
            "Orchard Honey",
            "Duskpetal Resin",
            "Hazeleaf",
        )
        self.assertFalse(ItemTemplate.objects.filter(name__in=dropped_ingredient_names).exists())
