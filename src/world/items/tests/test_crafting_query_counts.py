"""Query-budget regression guard for the crafting hot path (#1031).

Locks in the query budgets for ``craft_attach_facet`` (via ``run_crafting_recipe``)
and ``build_crafting_quote`` so that N+1 regressions are caught at the test tier
rather than discovered in production profiling.

## What these tests guard

``run_crafting_recipe`` pipeline (per call):
  1. CraftingRecipe GET — 1 query
  2. FacetAttachHandler.pre_validate (assert_facet_attachable): EXISTS + COUNT — 2 queries
  3. stage_and_assert_affordable:
     a. ActionPointConfig × 2 (get_default_maximum called for maximum + current) — 2 q
     b. ActionPointPool GET — 1 query
     c. CharacterAnima filter.first — 1 query
     d. material_requirements.select_related — 1 query (all requirement rows in one hit)
     e. ItemInstance filter for holder inventory — 1 query (all matching items in one hit)
  4. perform_check / _build_forced_check_result:
     a. _get_character_level: CharacterClassLevel × 2 queries
     b. _calculate_trait_points: check_type.traits.select_related + trait-values + traits
        + PointConversionRange — 4 queries
     c. _calculate_aspect_bonus: CharacterPathHistory filter — 1 query (returns None)
     d. CheckRank.get_rank_for_points × 2 + ResultChart.get_chart_for_difference — 3 q
  5. consequence_rows.select_related — 1 query (all rows in one hit, not per-row)
  6. consume_cost:
     a. ActionPointConfig × 2 + ActionPointPool GET + pool.spend UPDATE — 4 queries
     b. anima sufficiency guard (filter.first) — 1 query (#1243; symmetric with the AP
        path, asserts the staged anima is still affordable before deducting)
     c. deduct_anima → anima GET + unique check + UPDATE — 3 queries
     d. consume_pks → Django cascade collect (batched IN-lists per FK) + DELETE — ~14 q
  7. apply_resolution → apply_all_effects — 0 queries for a consequence with no effects
  8. resolve_capped_tier:
     a. CraftingSkillCap.for_skill — 1 query (single ORDER BY + LIMIT, not per-row)
     b. QualityTier.for_score — 1 query
  9. FacetAttachHandler.apply (attach_facet_to_item):
     a. assert_facet_attachable: EXISTS + COUNT — 2 queries
     b. ItemFacet.objects.create — 1 query (INSERT)
     c. EquippedItem.objects.filter(item_instance=) — 1 query (item not equipped in test)

``build_crafting_quote`` pipeline (per call):
  1. CraftingRecipe GET — 1 query
  2. ActionPointConfig × 2 + ActionPointPool GET — 3 queries
  3. CharacterAnima filter.first — 1 query
  4. material_requirements.select_related — 1 query (all rows in one hit)
  5. ItemInstance filter for holder inventory — 1 query (all matching items in one hit)
  6. get_trait_value → trait lookup — 1 query
  7. CraftingSkillCap.for_skill — 1 query (single ORDER BY + LIMIT, not per-cap-row)
  8. consequence_rows.select_related — 1 query (all rows in one hit)

N+1 invariants verified:
  - ``consequence_rows`` uses SELECT + ``select_related("consequence",
    "consequence__outcome_tier")`` — one query regardless of pool size.
  - ``material_requirements`` uses SELECT + ``select_related("item_template",
    "min_quality_tier")`` — one query regardless of how many requirements exist.
  - The Python iteration over ``available`` in gather_consumable_pks never issues
    per-item queries (all instances fetched in one bulk SELECT beforehand).
  - ``CraftingSkillCap.for_skill`` issues exactly one SELECT per call (filter +
    order_by("-min_skill_value") + LIMIT 1); ladder size does not scale the count.
  - Django's cascade collect before the material DELETE issues one IN-list query per
    related model (O(related_model_count), NOT O(material_count)); the IN-list batches
    all material PKs into a single round-trip per related model.
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.action_points.models import ActionPointPool
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import ConsequenceFactory
from world.checks.test_helpers import force_check_outcome
from world.items.crafting.constants import CostConsumption
from world.items.crafting.models import CraftingMaterialRequirement
from world.items.crafting.services import build_crafting_quote
from world.items.factories import (
    CraftingMaterialRequirementFactory,
    CraftingRecipeConsequenceFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
    wire_enchanting_crafting,
)
from world.items.services.crafting import craft_attach_facet
from world.magic.factories import FacetFactory
from world.traits.factories import CharacterTraitValueFactory, CheckOutcomeFactory


def _enchanting_trait():
    from world.traits.models import Trait

    return Trait.objects.get(name="Enchanting")


class CraftAttachFacetQueryCountTests(TestCase):
    """Pin the query budget for one successful ``craft_attach_facet`` call.

    The recipe has ≥2 consequence rows + ≥2 skill-cap rows + ≥1 material
    requirement so any per-row N+1 in those loops would manifest as extra
    queries relative to the pinned baseline.
    """

    def setUp(self) -> None:
        from world.items.models import QualityTier
        from world.magic.models import CharacterAnima

        self.recipe = wire_enchanting_crafting(base_difficulty=0)
        # wire_enchanting_crafting seeds 3 CraftingSkillCap rows + 2 consequence rows.
        # Add a 3rd consequence so the pool has ≥3 rows; per-row N+1 would be visible.
        extra_outcome = CheckOutcomeFactory(name="CQC_ExtraOutcome", success_level=1)
        extra_cons = ConsequenceFactory(outcome_tier=extra_outcome, label="CQC extra consequence")
        CraftingRecipeConsequenceFactory(
            recipe=self.recipe,
            consequence=extra_cons,
            cost_consumption=CostConsumption.PARTIAL,
        )

        # Add 2 material requirements (different templates) to catch per-requirement N+1.
        mat_tpl_1 = ItemTemplateFactory(name="CQCMat1")
        mat_tpl_2 = ItemTemplateFactory(name="CQCMat2")
        self.recipe.action_point_cost = 2
        self.recipe.anima_cost = 1
        self.recipe.save()
        CraftingMaterialRequirement.objects.filter(recipe=self.recipe).delete()
        CraftingMaterialRequirementFactory(recipe=self.recipe, item_template=mat_tpl_1, quantity=1)
        CraftingMaterialRequirementFactory(recipe=self.recipe, item_template=mat_tpl_2, quantity=1)

        # Character setup.
        self.sheet = CharacterSheetFactory()
        self.account = AccountFactory()
        self.character = self.sheet.character

        # Give the character enough skill to qualify for the Fine cap band (skill >= 40).
        CharacterTraitValueFactory(character=self.character, trait=_enchanting_trait(), value=50)

        # Fund AP and Anima.
        pool = ActionPointPool.get_or_create_for_character(self.character)
        pool.current = 10
        pool.save()
        CharacterAnima.objects.update_or_create(
            character=self.character,
            defaults={"current": 10, "maximum": 10},
        )

        # Seed 2 material instances in the character's inventory.
        common = QualityTier.objects.get(name="Common")
        ItemInstanceFactory(
            template=mat_tpl_1,
            quantity=2,
            quality_tier=common,
            holder_character_sheet=self.sheet,
        )
        ItemInstanceFactory(
            template=mat_tpl_2,
            quantity=2,
            quality_tier=common,
            holder_character_sheet=self.sheet,
        )

        # Target item (with capacity for a facet).
        item_tpl = ItemTemplateFactory(name="CQCItem", facet_capacity=3)
        self.item = ItemInstanceFactory(
            template=item_tpl,
            holder_character_sheet=self.sheet,
        )
        self.facet = FacetFactory(name="CQCFacet")

        # Force a successful outcome (success_level=2, which ≥ min_success_level=1).
        self.success_outcome = CheckOutcomeFactory(name="CQC_Success", success_level=2)

    def test_craft_attach_facet_query_count(self) -> None:
        """craft_attach_facet must not scale queries with consequence/cap/material row count.

        Pinned at 66 queries (measured on SQLite; #1031 baseline 63 + 1 for the #1243
        symmetric anima-sufficiency guard in consume_cost + 1 for the #1688
        specialization-composition lookup in perform_check / _build_forced_check_result —
        an unconditional sibling of the existing trait/aspect composition queries + 1 for
        the #1770 stories.Stake.subject_item inbound FK (SET_NULL) the delete-collector now
        scans when consumed material ItemInstances are hard-deleted). Breakdown:
          - ~14 SAVEPOINT/RELEASE pairs from @transaction.atomic nesting
          - ~13 Django cascade collect queries before material DELETE (batched IN-lists
            per FK-related model; O(related_models) not O(material_count))
          - ~4 ActionPointConfig duplicate reads from get_or_create_for_character × 2
          - ~34 real reads/writes covering the pipeline described in the module docstring

        consequence_rows: single SELECT (query 21) — NOT one per row.
        material_requirements: single SELECT (query 9) — NOT one per requirement.
        CraftingSkillCap.for_skill: single SELECT (query 53) — NOT one per cap row.

        The guard fires when per-row queries are introduced: even 1 extra query per
        consequence row (3 rows) would push the count up by ≥3, exceeding this ceiling.

        ``flush_test_caches`` at the start ensures the SharedMemoryModel identity map
        is clean — without it, a lookup-model object (e.g. QualityTier, ActionPointConfig)
        cached from a preceding test in a different shard ordering can satisfy a read
        from the identity map instead of the DB, reducing the count by 1 and making the
        pinned count fragile across CI shard regroupings.
        """
        from core.testing import flush_test_caches

        flush_test_caches()
        with force_check_outcome(self.success_outcome):
            with self.assertNumQueries(66):
                result = craft_attach_facet(
                    crafter_account=self.account,
                    crafter_character=self.character,
                    item_instance=self.item,
                    facet=self.facet,
                )

        self.assertTrue(result.attached)
        self.assertIsNotNone(result.quality_tier)


class BuildCraftingQuoteQueryCountTests(TestCase):
    """Pin the query budget for one ``build_crafting_quote`` call.

    The recipe has ≥2 consequence rows + ≥2 skill-cap rows + ≥1 material
    requirement so any per-row N+1 would manifest as extra queries.
    ``build_crafting_quote`` does not mutate state or roll; its budget is
    substantially lower than ``craft_attach_facet``.
    """

    def setUp(self) -> None:
        from world.items.models import QualityTier
        from world.magic.models import CharacterAnima

        self.recipe = wire_enchanting_crafting(base_difficulty=0)
        # Add a 3rd consequence to verify the consequence fetch is a single bulk query.
        extra_outcome = CheckOutcomeFactory(name="BCQ_ExtraOutcome", success_level=1)
        extra_cons = ConsequenceFactory(outcome_tier=extra_outcome, label="BCQ extra consequence")
        CraftingRecipeConsequenceFactory(
            recipe=self.recipe,
            consequence=extra_cons,
            cost_consumption=CostConsumption.PARTIAL,
        )

        mat_tpl_1 = ItemTemplateFactory(name="BCQMat1")
        mat_tpl_2 = ItemTemplateFactory(name="BCQMat2")
        self.recipe.action_point_cost = 2
        self.recipe.anima_cost = 1
        self.recipe.save()
        CraftingMaterialRequirement.objects.filter(recipe=self.recipe).delete()
        CraftingMaterialRequirementFactory(recipe=self.recipe, item_template=mat_tpl_1, quantity=1)
        CraftingMaterialRequirementFactory(recipe=self.recipe, item_template=mat_tpl_2, quantity=1)

        # Character setup.
        self.sheet = CharacterSheetFactory()
        self.account = AccountFactory()
        self.character = self.sheet.character

        CharacterTraitValueFactory(character=self.character, trait=_enchanting_trait(), value=50)

        pool = ActionPointPool.get_or_create_for_character(self.character)
        pool.current = 10
        pool.save()
        CharacterAnima.objects.update_or_create(
            character=self.character,
            defaults={"current": 10, "maximum": 10},
        )

        common = QualityTier.objects.get(name="Common")
        ItemInstanceFactory(
            template=mat_tpl_1,
            quantity=2,
            quality_tier=common,
            holder_character_sheet=self.sheet,
        )
        ItemInstanceFactory(
            template=mat_tpl_2,
            quantity=2,
            quality_tier=common,
            holder_character_sheet=self.sheet,
        )

    def test_build_crafting_quote_query_count(self) -> None:
        """build_crafting_quote must not scale queries with consequence/cap/material row count.

        Pinned at 11 queries (measured on SQLite, #1031 baseline):
          recipe GET (1) + ActionPointConfig × 2 + ActionPointPool GET (3)
          + CharacterAnima filter.first (1) + material_requirements select_related (1)
          + ItemInstance IN-list (1) + trait-value lookup (1)
          + CraftingSkillCap.for_skill (1) + consequence_rows select_related (1)
          = 11 queries.

        material_requirements: single SELECT — NOT one per requirement.
        CraftingSkillCap.for_skill: single SELECT — NOT one per cap row.
        consequence_rows: single SELECT — NOT one per consequence row.

        Adding even 1 extra per-row query across 3 consequence rows or 2 material
        requirements would push the count above this ceiling.
        """
        from world.items.crafting.constants import CraftingRecipeKind

        with self.assertNumQueries(11):
            quote = build_crafting_quote(
                kind=CraftingRecipeKind.FACET_ATTACH,
                crafter_character=self.character,
                crafter_character_sheet=self.sheet,
                target=None,
            )

        self.assertIsNotNone(quote)
        self.assertTrue(quote.affordable)
        self.assertIsNotNone(quote.max_quality_tier)
        self.assertGreaterEqual(len(quote.failure_risk), 2)
