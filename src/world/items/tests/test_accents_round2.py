"""Tests for #2886: exclusion pairs, refinement doubling, removal, recycling."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.items.crafting.models import AccentExclusion, ItemAccent
from world.items.crafting.refinement import refinement_threshold
from world.items.crafting.services import _validate_accent_targets
from world.items.exceptions import (
    InvalidAccentTarget,
    NotItemOwner,
    RecycleNeedsGMApproval,
)
from world.items.factories import (
    CraftingMaterialRequirementFactory,
    CraftingRecipeFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
)
from world.items.models import AccentLevel, ItemInstance, RecycleRequest
from world.items.services.recycle import (
    recycle_item,
    remove_item_accent,
    request_recycle_approval,
    resolve_recycle_request,
)
from world.mechanics.factories import ModifierTargetFactory


def _accent_ladder() -> None:
    for level, name in ((1, "slightly"), (2, "modestly"), (3, "quite"), (4, "very")):
        AccentLevel.objects.get_or_create(level=level, defaults={"name": name})


class AccentExclusionTests(TestCase):
    def setUp(self) -> None:
        _accent_ladder()
        self.dramatic = ModifierTargetFactory(name="dramatic", is_styleable=True)
        self.unassuming = ModifierTargetFactory(name="unassuming", is_styleable=True)
        AccentExclusion.objects.create(target_a=self.dramatic, target_b=self.unassuming)

    def test_excluded_pair_rejected_in_one_request(self) -> None:
        with self.assertRaises(InvalidAccentTarget):
            _validate_accent_targets([self.dramatic, self.unassuming])

    def test_exclusion_checks_existing_accents_on_the_item(self) -> None:
        sheet = CharacterSheetFactory()
        item = ItemInstanceFactory(template=ItemTemplateFactory(), holder_character_sheet=sheet)
        ItemAccent.objects.create(
            item_instance=item, target=self.dramatic, level=AccentLevel.objects.get(level=2)
        )
        with self.assertRaises(InvalidAccentTarget):
            _validate_accent_targets([self.unassuming], item)

    def test_non_conflicting_pair_passes(self) -> None:
        menace = ModifierTargetFactory(name="menace", is_styleable=True)
        self.assertEqual(_validate_accent_targets([self.dramatic, menace]), [self.dramatic, menace])


class RefinementDoublingTests(TestCase):
    def test_each_accent_doubles_the_threshold(self) -> None:
        _accent_ladder()
        sheet = CharacterSheetFactory()
        item = ItemInstanceFactory(
            template=ItemTemplateFactory(value=1000), holder_character_sheet=sheet
        )
        self.assertEqual(refinement_threshold(item, 1), 40)  # pace ×4
        menace = ModifierTargetFactory(name="menace", is_styleable=True)
        allure = ModifierTargetFactory(name="allure", is_styleable=True)
        ItemAccent.objects.create(
            item_instance=item, target=menace, level=AccentLevel.objects.get(level=1)
        )
        self.assertEqual(refinement_threshold(item, 1), 80)
        ItemAccent.objects.create(
            item_instance=item, target=allure, level=AccentLevel.objects.get(level=1)
        )
        self.assertEqual(refinement_threshold(item, 1), 160)


class RemoveAccentTests(TestCase):
    def setUp(self) -> None:
        _accent_ladder()
        self.sheet = CharacterSheetFactory()
        self.item = ItemInstanceFactory(
            template=ItemTemplateFactory(), holder_character_sheet=self.sheet
        )
        self.menace = ModifierTargetFactory(name="menace", is_styleable=True)
        ItemAccent.objects.create(
            item_instance=self.item, target=self.menace, level=AccentLevel.objects.get(level=3)
        )

    def test_owner_removes_accent(self) -> None:
        remove_item_accent(item_instance=self.item, target=self.menace, actor_sheet=self.sheet)
        self.assertFalse(ItemAccent.objects.filter(item_instance=self.item).exists())

    def test_non_owner_rejected(self) -> None:
        stranger = CharacterSheetFactory()
        with self.assertRaises(NotItemOwner):
            remove_item_accent(item_instance=self.item, target=self.menace, actor_sheet=stranger)
        self.assertTrue(ItemAccent.objects.filter(item_instance=self.item).exists())


class RecycleTests(TestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.template = ItemTemplateFactory(value=500)
        self.item = ItemInstanceFactory(template=self.template, holder_character_sheet=self.sheet)

    def test_owner_recycles_plain_item(self) -> None:
        item_pk = self.item.pk
        result = recycle_item(item_instance=self.item, actor_sheet=self.sheet)
        self.assertEqual(result.salvaged, ())
        self.assertFalse(ItemInstance.objects.filter(pk=item_pk).exists())

    def test_salvage_returns_fraction_of_recipe_materials(self) -> None:
        from world.items.crafting.models import CraftedItemRecipe
        from world.items.factories import QualityTierFactory

        material = ItemTemplateFactory(name="Standard Steel Test")
        recipe = CraftingRecipeFactory(output_item_template=self.template)
        CraftingMaterialRequirementFactory(recipe=recipe, item_template=material, quantity=4)
        tier = QualityTierFactory(name="Average", numeric_min=0, numeric_max=99, sort_order=3)
        CraftedItemRecipe.objects.create(item_instance=self.item, recipe=recipe, quality_tier=tier)
        result = recycle_item(item_instance=self.item, actor_sheet=self.sheet)
        self.assertEqual(result.salvaged, (("Standard Steel Test", 2),))  # 4 × 0.5
        salvage = ItemInstance.objects.filter(
            template=material, holder_character_sheet=self.sheet
        ).first()
        assert salvage is not None
        self.assertEqual(salvage.quantity, 2)

    def test_non_owner_rejected(self) -> None:
        stranger = CharacterSheetFactory()
        with self.assertRaises(NotItemOwner):
            recycle_item(item_instance=self.item, actor_sheet=stranger)

    def test_story_protected_needs_gm_approval(self) -> None:
        from world.societies.factories import LegendEntryFactory

        deed = LegendEntryFactory(is_active=True)
        self.item.legend_deeds.add(deed)
        with self.assertRaises(RecycleNeedsGMApproval):
            recycle_item(item_instance=self.item, actor_sheet=self.sheet)

        request = request_recycle_approval(item_instance=self.item, actor_sheet=self.sheet)
        from world.gm.factories import GMProfileFactory

        resolve_recycle_request(request=request, gm_profile=GMProfileFactory(), approve=True)
        item_pk = self.item.pk
        recycle_item(item_instance=self.item, actor_sheet=self.sheet)
        self.assertFalse(ItemInstance.objects.filter(pk=item_pk, destroyed_at=None).exists())

    def test_denied_request_still_blocks(self) -> None:
        from world.gm.factories import GMProfileFactory
        from world.societies.factories import LegendEntryFactory

        self.item.legend_deeds.add(LegendEntryFactory(is_active=True))
        request = request_recycle_approval(item_instance=self.item, actor_sheet=self.sheet)
        resolve_recycle_request(request=request, gm_profile=GMProfileFactory(), approve=False)
        with self.assertRaises(RecycleNeedsGMApproval):
            recycle_item(item_instance=self.item, actor_sheet=self.sheet)
        self.assertEqual(RecycleRequest.objects.get(pk=request.pk).status, "denied")


class QualityLuckTests(TestCase):
    """The craft's own d100 spreads the quality score (#2886)."""

    def test_hot_and_cold_rolls_shift_the_score(self) -> None:
        from types import SimpleNamespace

        from world.items.services.crafting import compute_quality_score

        hot = SimpleNamespace(total_points=50, success_level=1, effective_roll=100)
        cold = SimpleNamespace(total_points=50, success_level=1, effective_roll=1)
        par = SimpleNamespace(total_points=50, success_level=1, effective_roll=45)
        base = compute_quality_score(par, step=10, min_success_level=1)
        self.assertEqual(base, 50)
        self.assertEqual(compute_quality_score(hot, step=10, min_success_level=1), 61)
        self.assertEqual(compute_quality_score(cold, step=10, min_success_level=1), 41)

    def test_no_roll_means_no_luck(self) -> None:
        from types import SimpleNamespace

        from world.items.services.crafting import compute_quality_score

        forced = SimpleNamespace(total_points=50, success_level=1, effective_roll=0)
        self.assertEqual(compute_quality_score(forced, step=10, min_success_level=1), 50)


class ThreadCheckEdgeTests(TestCase):
    """Woven threads add to the craft roll, not just the ceiling (#2886)."""

    def test_thread_contribution_built_per_thread(self) -> None:
        from world.items.crafting.services import _thread_check_contributions
        from world.items.factories import wire_enchanting_crafting
        from world.magic.factories import ThreadFactory

        recipe = wire_enchanting_crafting(base_difficulty=0)
        sheet = CharacterSheetFactory()
        self.assertEqual(_thread_check_contributions(sheet.character, recipe), [])
        ThreadFactory(owner=sheet, target_trait=recipe.skill_trait)
        ThreadFactory(
            owner=sheet,
            target_trait=recipe.skill_trait,
            resonance__name="SecondResonance",
        )
        contribs = _thread_check_contributions(sheet.character, recipe)
        self.assertEqual(len(contribs), 1)
        self.assertEqual(contribs[0].value, 20)
        self.assertEqual(contribs[0].source_label, "Woven threads")


class AccentArchetypeAllowanceTests(TestCase):
    """No stealthy jewelry (#2886): the ratified archetype allowlist."""

    def setUp(self) -> None:
        _accent_ladder()
        from world.items.crafting.models import AccentArchetypeAllowance

        self.stealthy = ModifierTargetFactory(name="stealthy", is_styleable=True)
        for archetype in ("clothing", "robe", "light_armor"):
            AccentArchetypeAllowance.objects.create(target=self.stealthy, gear_archetype=archetype)

    def test_disallowed_archetype_rejected(self) -> None:
        from world.items.constants import GearArchetype

        jewelry = ItemTemplateFactory(gear_archetype=GearArchetype.JEWELRY)
        with self.assertRaises(InvalidAccentTarget):
            _validate_accent_targets([self.stealthy], template=jewelry)

    def test_allowed_archetype_passes(self) -> None:
        from world.items.constants import GearArchetype

        cloak = ItemTemplateFactory(gear_archetype=GearArchetype.CLOTHING)
        self.assertEqual(_validate_accent_targets([self.stealthy], template=cloak), [self.stealthy])

    def test_unlisted_target_is_unrestricted(self) -> None:
        from world.items.constants import GearArchetype

        custom = ModifierTargetFactory(name="custom-axis", is_styleable=True)
        jewelry = ItemTemplateFactory(gear_archetype=GearArchetype.JEWELRY)
        self.assertEqual(_validate_accent_targets([custom], template=jewelry), [custom])
