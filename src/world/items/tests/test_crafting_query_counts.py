"""Query-budget regression guard for the crafting hot path (#1031).

Locks in the query budgets for ``craft_attach_facet`` (via ``run_crafting_recipe``)
and ``build_crafting_quote`` so that N+1 regressions are caught at the test tier
rather than discovered in production profiling.

## What these tests guard

``run_crafting_recipe`` pipeline (per call):
  1. CraftingRecipe GET — 1 query
  2. FacetAttachHandler.pre_validate (assert_facet_attachable): EXISTS + COUNT — 2 queries
  2.5. Station gate (#1234) — _resolve_active_lab_station: RoomProfile filter.first
       + RoomFeatureInstance filter.first + LabStationDetails filter.first — 3 queries
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
  4.5. Station wear (#1234) — unconditional durability decrement + save(update_fields=)
       — SAVEPOINT + UPDATE + RELEASE SAVEPOINT — 3 queries
  5. consequence_rows.select_related — 1 query (all rows in one hit, not per-row)
  6. consume_cost:
     a. ActionPointConfig × 2 + ActionPointPool GET + pool.spend UPDATE — 4 queries
     b. anima sufficiency guard (filter.first) — 1 query (#1243; symmetric with the AP
        path, asserts the staged anima is still affordable before deducting)
     c. deduct_anima → anima GET + unique check + UPDATE — 3 queries
     d. consume_materials → per-instance .save(update_fields) or .delete() — ~2 q
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

from evennia_extensions.factories import AccountFactory, RoomProfileFactory
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
    install_full_lab_station,
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
        # requires_station defaults True (#1234) — install a Lab station in the
        # crafter's room so this pre-existing pinned-query test can still craft.
        room_profile = RoomProfileFactory()
        self.character.location = room_profile.objectdb
        self.character.save()
        install_full_lab_station(room_profile)

        # Give the character enough skill to qualify for the Fine cap band (skill >= 40).
        CharacterTraitValueFactory(
            character=self.character.sheet_data, trait=_enchanting_trait(), value=50
        )

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

        Pinned at 75 queries (measured on Postgres CI; SQLite runs 76 — one extra
        SELECT from a SharedMemoryModel identity-map miss). The 1-query difference
        is test-ordering-dependent: a preceding test may warm the identity map for
        a lookup model (ActionPointConfig, QualityTier), eliminating one SELECT.
        The guard's purpose is catching N+1 *increases* — a per-row N+1 over 3
        consequence rows would push the count up by ≥3, exceeding any baseline.
        Prior baselines: #1031 (63) → #1243 (+1 anima guard) → #1688 (+1 spec)
        → #1770 (+1 Stake.subject_item SET_NULL cascade) → shard rebalance (-1
        from cache-hit ordering) → #1234 (+6: the station gate's
        ``_resolve_active_lab_station`` resolve — RoomProfile + RoomFeatureInstance
        + LabStationDetails lookups, 3 queries — plus the unconditional wear-decrement
        save wrapped in a SAVEPOINT/UPDATE/RELEASE, 3 queries) → #1771 (+1
        TreasuredSubject.subject_item SET_NULL cascade — one constant UPDATE when a
        material ItemInstance is consumed, same shape as the #1770 Stake.subject_item
        bump; does NOT scale with treasured-row count) → #2001 (+1
        StoryProtectedSubject.subject_item SET_NULL cascade — one constant UPDATE
        in the Django cascade-collect when a material ItemInstance is consumed,
        same shape as the #1770/#1771 bumps; does NOT scale with protected-subject
        row count) → #2066 (+2: WareListing.item_instance CASCADE adds one
        collect SELECT and MarketSale.item_instance SET_NULL adds one constant
        UPDATE when a material ItemInstance is consumed; neither scales with
        listing/sale row count).

        consequence_rows: single SELECT — NOT one per row.
        material_requirements: single SELECT — NOT one per requirement.
        CraftingSkillCap.for_skill: single SELECT — NOT one per cap row.
        """
        with force_check_outcome(self.success_outcome):
            # Postgres runs 75: a preceding test in the shard warms the
            # SharedMemoryModel identity map for a lookup model (e.g.
            # ActionPointConfig), eliminating one SELECT. SQLite runs 89
            # (no cache hit — different test isolation). The 1-query gap is
            # ordering-dependent, not a regression — a per-row N+1 over 3
            # consequence rows would push either count up by ≥3.
            # +1 (both vendors) from the main merge that brought #2266/#2273's
            # item-prose + market cascades into this branch — a constant SELECT/
            # UPDATE, not a per-row N+1 (which would push the count up by ≥3).
            # +1 SQLite (#2249): importing DisguiseKind/ConcealmentLevel from
            # forms.models into items.models changed identity-map warm-up
            # ordering, adding one constant SELECT (not a per-row N+1).
            # Postgres 86→88; SQLite 87→89.
            # +2 (both vendors, #1985): EstateClaim.item PROTECT adds one
            # collect SELECT and Bequest.item SET_NULL adds one constant UPDATE
            # when a material ItemInstance is consumed — same shape as the
            # #2066 market cascades; neither scales with claim/bequest rows.
            # Postgres 88→90; SQLite 89→91.
            # +1 (both vendors, #1825): CrimeEvidence.item_instance SET_NULL
            # adds one constant UPDATE in the same consume cascade — same
            # shape again; never scales with evidence rows.
            # Postgres 90→91; SQLite 91→92.
            # +1 (both vendors, #2359): ItemInstance.legend_deeds M2M through
            # table adds one constant SELECT in the Django cascade-collect when
            # a material ItemInstance is consumed — same shape as the market/
            # estate/evidence bumps; never scales with linked-deed count.
            # Postgres 91→92; SQLite 92→93.
            from django.db import connection
            from django.test.utils import CaptureQueriesContext

            # Band, not exact count (2026-07 shard rebalance): whether a
            # SharedMemoryModel lookup (RoomProfile, ActionPointConfig, ...)
            # hits the identity map depends on which tests ran earlier in the
            # process, so the exact count wobbles ±1 with suite composition on
            # BOTH vendors — the old exact-per-vendor pins broke every time
            # the CI shard groupings changed. The guard's purpose is catching
            # per-row N+1s, and those add ≥3 (3 consequence rows), which blows
            # past the band. Observed: 74 (cold identity map) / 75 (warm).
            #
            # #2454: consume_materials replaced the wholesale DELETE cascade
            # (14+ cascade-collect queries per material ItemInstance) with a
            # per-instance .save(update_fields=["quantity"]) — the test setup
            # uses quantity=2 materials with quantity=1 requirements, so the
            # common case is now a partial-consume (save, not delete). The band
            # dropped from 91-94 to 74-76.
            with CaptureQueriesContext(connection) as ctx:
                result = craft_attach_facet(
                    crafter_account=self.account,
                    crafter_character=self.character,
                    item_instance=self.item,
                    facet=self.facet,
                )
            executed = len(ctx.captured_queries)
            self.assertTrue(
                74 <= executed <= 76,
                f"{executed} queries executed, expected 75 ±1 identity-map "
                f"wobble (band 74-76). A jump of >=3 means a per-row N+1.",
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
        # This test pins the consequence/cap/material query budget, not the
        # station-status budget (#1234) — station status is covered separately
        # by CraftingQuoteStationStatusTests below.
        self.recipe.requires_station = False
        self.recipe.save()
        CraftingMaterialRequirement.objects.filter(recipe=self.recipe).delete()
        CraftingMaterialRequirementFactory(recipe=self.recipe, item_template=mat_tpl_1, quantity=1)
        CraftingMaterialRequirementFactory(recipe=self.recipe, item_template=mat_tpl_2, quantity=1)

        # Character setup.
        self.sheet = CharacterSheetFactory()
        self.account = AccountFactory()
        self.character = self.sheet.character

        CharacterTraitValueFactory(
            character=self.character.sheet_data, trait=_enchanting_trait(), value=50
        )

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


class CraftingQuoteStationStatusTests(TestCase):
    """``build_crafting_quote``'s read-only ``station_status`` field (#1234)."""

    def setUp(self) -> None:
        from evennia_extensions.factories import RoomProfileFactory
        from world.items.crafting.models import LabStationDetails
        from world.room_features.constants import RoomFeatureServiceStrategy
        from world.room_features.factories import RoomFeatureInstanceFactory, RoomFeatureKindFactory

        self.recipe = wire_enchanting_crafting()
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        room_profile = RoomProfileFactory()
        self.character.location = room_profile.objectdb
        self.character.save()
        kind = RoomFeatureKindFactory(service_strategy=RoomFeatureServiceStrategy.LAB)
        instance = RoomFeatureInstanceFactory(room_profile=room_profile, feature_kind=kind, level=1)
        self.station = LabStationDetails.objects.create(
            feature_instance=instance, durability=3, max_durability=20
        )

    def test_station_status_present_and_not_affordable_when_broken(self) -> None:
        from world.items.crafting.constants import CraftingRecipeKind

        self.station.durability = 0
        self.station.save(update_fields=["durability"])
        quote = build_crafting_quote(
            kind=CraftingRecipeKind.FACET_ATTACH,
            crafter_character=self.character,
            crafter_character_sheet=self.sheet,
            target=None,
        )
        self.assertIsNotNone(quote.station_status)
        self.assertTrue(quote.station_status.present)
        self.assertTrue(quote.station_status.is_broken)
        self.assertFalse(quote.affordable)

    def test_station_status_reports_present_and_not_broken_when_healthy(self) -> None:
        from world.items.crafting.constants import CraftingRecipeKind

        quote = build_crafting_quote(
            kind=CraftingRecipeKind.FACET_ATTACH,
            crafter_character=self.character,
            crafter_character_sheet=self.sheet,
            target=None,
        )
        self.assertIsNotNone(quote.station_status)
        self.assertTrue(quote.station_status.present)
        self.assertFalse(quote.station_status.is_broken)
        self.assertEqual(quote.station_status.durability, 3)
        self.assertEqual(quote.station_status.max_durability, 20)
        self.assertEqual(quote.station_status.feature_instance_id, self.station.feature_instance_id)

    def test_station_status_missing_and_not_affordable_when_no_station_in_room(self) -> None:
        from world.items.crafting.constants import CraftingRecipeKind

        self.station.delete()
        quote = build_crafting_quote(
            kind=CraftingRecipeKind.FACET_ATTACH,
            crafter_character=self.character,
            crafter_character_sheet=self.sheet,
            target=None,
        )
        self.assertIsNotNone(quote.station_status)
        self.assertFalse(quote.station_status.present)
        self.assertTrue(quote.station_status.is_broken)
        self.assertIsNone(quote.station_status.feature_instance_id)
        self.assertFalse(quote.affordable)

    def test_station_status_none_when_recipe_does_not_require_one(self) -> None:
        from world.items.crafting.constants import CraftingRecipeKind

        self.recipe.requires_station = False
        self.recipe.save(update_fields=["requires_station"])
        quote = build_crafting_quote(
            kind=CraftingRecipeKind.FACET_ATTACH,
            crafter_character=self.character,
            crafter_character_sheet=self.sheet,
            target=None,
        )
        self.assertIsNone(quote.station_status)
