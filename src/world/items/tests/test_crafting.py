from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.items.exceptions import FacetAlreadyAttached, FacetCapacityExceeded
from world.items.factories import (
    ItemFacetFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
    QualityTierFactory,
)
from world.traits.factories import CharacterTraitValueFactory


class QualityTierForScoreTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.common = QualityTierFactory(name="Common", numeric_min=0, numeric_max=29, sort_order=0)
        cls.fine = QualityTierFactory(name="Fine", numeric_min=30, numeric_max=69, sort_order=1)
        cls.master = QualityTierFactory(
            name="Masterwork", numeric_min=70, numeric_max=200, sort_order=2
        )

    def test_score_resolves_to_containing_tier(self) -> None:
        from world.items.models import QualityTier

        self.assertEqual(QualityTier.for_score(10), self.common)
        self.assertEqual(QualityTier.for_score(30), self.fine)
        self.assertEqual(QualityTier.for_score(69), self.fine)
        self.assertEqual(QualityTier.for_score(150), self.master)

    def test_below_all_ranges_clamps_to_lowest(self) -> None:
        from world.items.models import QualityTier

        self.assertEqual(QualityTier.for_score(-5), self.common)

    def test_above_all_ranges_clamps_to_highest(self) -> None:
        from world.items.models import QualityTier

        self.assertEqual(QualityTier.for_score(9999), self.master)


class ComputeQualityScoreTests(TestCase):
    def _result(self, *, total_points: int, success_level: int):
        from types import SimpleNamespace

        return SimpleNamespace(total_points=total_points, success_level=success_level)

    def test_score_is_points_plus_stepped_success(self) -> None:
        from world.items.services.crafting import compute_quality_score

        score = compute_quality_score(
            self._result(total_points=40, success_level=3), step=10, min_success_level=1
        )
        self.assertEqual(score, 40 + (3 - 1) * 10)  # 60

    def test_success_at_minimum_adds_no_bonus(self) -> None:
        from world.items.services.crafting import compute_quality_score

        score = compute_quality_score(
            self._result(total_points=40, success_level=1), step=10, min_success_level=1
        )
        self.assertEqual(score, 40)


class AssertFacetAttachableTests(TestCase):
    def test_raises_when_capacity_full(self) -> None:
        from world.items.services.facets import assert_facet_attachable
        from world.magic.factories import FacetFactory

        template = ItemTemplateFactory(facet_capacity=0)
        item = ItemInstanceFactory(template=template)
        with self.assertRaises(FacetCapacityExceeded):
            assert_facet_attachable(item, FacetFactory())

    def test_raises_when_duplicate(self) -> None:
        from world.items.services.facets import assert_facet_attachable
        from world.magic.factories import FacetFactory

        template = ItemTemplateFactory(facet_capacity=3)
        item = ItemInstanceFactory(template=template)
        facet = FacetFactory()
        ItemFacetFactory(item_instance=item, facet=facet)
        with self.assertRaises(FacetAlreadyAttached):
            assert_facet_attachable(item, facet)


class WireEnchantingTests(TestCase):
    def test_wires_trait_checktype_and_recipes(self) -> None:
        from world.items.crafting.constants import CraftingRecipeKind
        from world.items.crafting.models import CraftingRecipe
        from world.items.factories import wire_enchanting_crafting

        recipe = wire_enchanting_crafting(base_difficulty=10)
        self.assertEqual(recipe.kind, CraftingRecipeKind.FACET_ATTACH)
        self.assertIsNotNone(recipe.check_type)
        self.assertEqual(recipe.base_difficulty, 10)
        # Both recipe kinds are wired and share the Enchanting check.
        style_recipe = CraftingRecipe.objects.get(kind=CraftingRecipeKind.STYLE_ATTACH)
        self.assertEqual(style_recipe.check_type, recipe.check_type)
        # Skill caps + consequence pool are seeded for integration tests.
        self.assertTrue(recipe.skill_caps.exists())
        self.assertTrue(recipe.consequence_rows.exists())


class CraftAttachFacetTests(TestCase):
    def setUp(self) -> None:
        from evennia_extensions.factories import RoomProfileFactory
        from world.items.factories import install_full_lab_station, wire_enchanting_crafting
        from world.magic.factories import FacetFactory
        from world.traits.models import Trait

        # wire_enchanting_crafting seeds the Common/Fine/Masterwork tier ladder.
        self.recipe = wire_enchanting_crafting(base_difficulty=0)
        self.sheet = CharacterSheetFactory()
        self.account = AccountFactory()
        CharacterTraitValueFactory(
            character=self.sheet,
            trait=Trait.objects.get(name="Enchanting"),
            value=50,
        )
        # requires_station defaults True (#1234) — install a Lab station in the
        # crafter's room so the pre-existing pipeline tests can still craft.
        room_profile = RoomProfileFactory()
        self.sheet.character.location = room_profile.objectdb
        self.sheet.character.save()
        install_full_lab_station(room_profile)
        template = ItemTemplateFactory(facet_capacity=3)
        self.item = ItemInstanceFactory(template=template, holder_character_sheet=self.sheet)
        self.facet = FacetFactory()

    def test_success_attaches_with_resolved_tier(self) -> None:
        from world.checks.test_helpers import force_check_outcome
        from world.items.models import ItemFacet
        from world.items.services.crafting import craft_attach_facet
        from world.traits.factories import CheckOutcomeFactory

        with force_check_outcome(CheckOutcomeFactory(name="CraftSuccess", success_level=2)):
            result = craft_attach_facet(
                crafter_account=self.account,
                crafter_character=self.sheet.character,
                item_instance=self.item,
                facet=self.facet,
            )
        self.assertTrue(result.attached)
        self.assertIsNotNone(result.item_facet)
        self.assertIsNotNone(result.quality_tier)
        self.assertEqual(
            ItemFacet.objects.filter(item_instance=self.item, facet=self.facet).count(), 1
        )

    def test_failed_roll_attaches_nothing(self) -> None:
        from world.checks.test_helpers import force_check_outcome
        from world.items.models import ItemFacet
        from world.items.services.crafting import craft_attach_facet
        from world.traits.factories import CheckOutcomeFactory

        with force_check_outcome(CheckOutcomeFactory(name="CraftBotch", success_level=-1)):
            result = craft_attach_facet(
                crafter_account=self.account,
                crafter_character=self.sheet.character,
                item_instance=self.item,
                facet=self.facet,
            )
        self.assertFalse(result.attached)
        self.assertIsNone(result.item_facet)
        self.assertFalse(ItemFacet.objects.filter(item_instance=self.item).exists())

    def test_capacity_full_raises_before_rolling(self) -> None:
        from world.checks.test_helpers import force_check_outcome
        from world.items.exceptions import FacetCapacityExceeded
        from world.items.services.crafting import craft_attach_facet
        from world.traits.factories import CheckOutcomeFactory

        full = ItemInstanceFactory(template=ItemTemplateFactory(facet_capacity=0))
        with force_check_outcome(
            CheckOutcomeFactory(name="ShouldNotRoll", success_level=2)
        ) as capture:
            with self.assertRaises(FacetCapacityExceeded):
                craft_attach_facet(
                    crafter_account=self.account,
                    crafter_character=self.sheet.character,
                    item_instance=full,
                    facet=self.facet,
                )
        self.assertIsNone(capture.check_type)  # perform_check never reached

    def test_unconfigured_check_type_raises(self) -> None:
        from world.items.exceptions import CraftingNotConfigured
        from world.items.services.crafting import craft_attach_facet

        self.recipe.check_type = None
        self.recipe.save()
        with self.assertRaises(CraftingNotConfigured):
            craft_attach_facet(
                crafter_account=self.account,
                crafter_character=self.sheet.character,
                item_instance=self.item,
                facet=self.facet,
            )

    def test_duplicate_facet_raises_before_rolling(self) -> None:
        from world.checks.test_helpers import force_check_outcome
        from world.items.exceptions import FacetAlreadyAttached
        from world.items.services.crafting import craft_attach_facet
        from world.traits.factories import CheckOutcomeFactory

        ItemFacetFactory(item_instance=self.item, facet=self.facet)
        with force_check_outcome(
            CheckOutcomeFactory(name="ShouldNotRoll", success_level=2)
        ) as capture:
            with self.assertRaises(FacetAlreadyAttached):
                craft_attach_facet(
                    crafter_account=self.account,
                    crafter_character=self.sheet.character,
                    item_instance=self.item,
                    facet=self.facet,
                )
        self.assertIsNone(capture.check_type)  # perform_check never reached
