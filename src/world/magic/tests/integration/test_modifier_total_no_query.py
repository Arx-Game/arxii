"""Regression test: get_modifier_total query budget (Spec D Task 44).

Goal: document and pin the DB query count for get_modifier_total after all
character-side handlers are warmed. Future regressions that bypass a handler
and slip in an extra query will increase N visibly.

Query budget analysis (as of Spec D PR1):
  The equipment walk paths introduced in Spec D §5.2 / §5.6 are NOT fully
  query-free even after warming, because three helper functions always hit the DB:

  1. get_modifier_breakdown (eager path):
       CharacterModifier.objects.filter(...).exists()
       → Always fires 1 query regardless of row count. Returns early if empty.

  2. _thread_pull_effects_for (passive facet bonuses):
       ThreadPullEffect.objects.filter(target_kind=FACET, resonance=..., tier=0, ...)
       → SharedMemoryModel caches instances by PK, NOT filter results.
       → Fires 1 query per unique (resonance, target, tier) call.

  3. covenant_role_bonus → role_base_bonus_for_target → CharacterSheet.current_level:
       cached_character_class_levels query (CharacterClassLevel select_related)
       → @cached_property fires once per sheet instance. NOT warmed by handler
       warming. Caches after first access.

  4. is_gear_compatible (covenant role bonus, covenants/services.py):
       GearArchetypeCompatibility.objects.filter(...).exists()
       → Same issue as ThreadPullEffect — filter/exists results are NOT
         identity-map cached.
       → Fires 1 query per unique (role, archetype) pair across equipped items.

  With the fixture below (1 FACET-kind thread + 1 equipped item + 1 covenant role):
    Query 1: CharacterModifier.exists() — eager path check (no rows → early return)
    Query 2: ThreadPullEffect.filter(...) — facet pull effects lookup
    Query 3: CharacterClassLevel select_related — current_level @cached_property
    Query 4: GearArchetypeCompatibility.filter(...).exists() — 1 equipped item
    Query 5: CovenantLevelBonus.filter(modifier_target=...).first() — covenant_level_bonus
             (#762) queries once per engaged member's modifier-total call; here it
             returns None (no row authored for this target) → contributes 0.
    Query 6: CharacterSheet.motif reverse-OneToOne fetch — passive_motif_style_bonuses
             (#1150) resolves the character's Motif for the resonance-linked target. The
             reverse OneToOne is keyed on character_id, not PK, so the SharedMemoryModel
             identity map can't serve it; one query fires. No Motif here → contributes 0.
    Query 7: CovenantRoleBonus.filter(covenant_role=..., modifier_target=...).first() —
             role_base_bonus_for_target (#985) fires once per engaged role's modifier-total
             call; returns None here (no authored row for this target) → contributes 0.
             Parallel to Query 5's CovenantLevelBonus lookup.
    Query 8: CrossingChoice.filter(thread=...) — passive_facet_crossing_bonuses (#1990)
             fires once per FACET-kind thread; returns no rows (no crossing choices
             authored) so it contributes 0 to the result.

  BASELINE = 8 queries.

  Note: after the first call, query 3 is cached via @cached_property, so repeated
  calls to get_modifier_total on the same sheet instance would yield 7 queries.
  The first-call baseline of 8 is the most conservative (and correct) measurement.

  Character-side handler walks (equipped_items.iter_item_facets,
  threads.threads_of_kind, covenant_roles.currently_engaged_roles) fire ZERO queries
  after warming — these are properly handler-cached. The 8 above are genuine
  "always-query" sites at the service function level. covenant_level_bonus only
  reaches its config query for ENGAGED members (it early-outs via the warm
  currently_engaged_roles handler otherwise).

  Future work (PR3): caching ThreadPullEffect, GearArchetypeCompatibility,
  CovenantLevelBonus, and CovenantRoleBonus lookups with an LRU or process-level dict
  would bring this to 1 (or 0 if CharacterModifier gets a per-character cache too).
  This test will need to be updated when that work lands.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase


class ModifierTotalQueryBudgetTests(TestCase):
    """Pins the query count for get_modifier_total after handlers are warm.

    Fixture covers BOTH equipment-walk paths:
    - passive_facet_bonuses (§5.2): FACET-kind thread + equipped item bearing the facet
    - covenant_role_bonus (§5.6): CharacterCovenantRole + GearArchetypeCompatibility row

    After calling iter_item_facets / threads_of_kind / currently_engaged_roles to warm the
    character-side handlers, exactly 7 queries remain (see module docstring).
    """

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import CharacterFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            GearArchetypeCompatibilityFactory,
        )
        from world.items.constants import BodyRegion, EquipmentLayer, GearArchetype
        from world.items.factories import (
            EquippedItemFactory,
            ItemFacetFactory,
            ItemInstanceFactory,
            ItemTemplateFactory,
            QualityTierFactory,
            TemplateSlotFactory,
        )
        from world.magic.constants import EffectKind, TargetKind
        from world.magic.factories import (
            FacetFactory,
            ResonanceFactory,
            ThreadFactory,
            ThreadPullEffectFactory,
        )
        from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory

        # 1. Character + CharacterSheet
        cls.character_obj = CharacterFactory(db_key="ModifierQueryBudgetChar")
        cls.sheet = CharacterSheetFactory(character=cls.character_obj, primary_persona=False)

        # 2. Resonance category target linked to a resonance — this puts the target
        #    in EQUIPMENT_RELEVANT_CATEGORIES ("resonance") so BOTH equipment walk
        #    paths fire.
        cls.resonance = ResonanceFactory()
        cls.resonance_category = ModifierCategoryFactory(name="resonance")
        cls.target = ModifierTargetFactory(
            name="ModifierQueryBudgetTarget",
            category=cls.resonance_category,
            target_resonance=cls.resonance,
        )

        # 3. Facet used as both thread anchor and item facet
        cls.facet = FacetFactory(name="ModifierQueryBudgetFacet")

        # 4. Quality tiers for the item and attachment
        cls.item_quality = QualityTierFactory(
            name="ModifierQueryBudgetItemQ", stat_multiplier=Decimal("1.00")
        )
        cls.attach_quality = QualityTierFactory(
            name="ModifierQueryBudgetAttachQ", stat_multiplier=Decimal("1.00")
        )

        # 5. ItemTemplate with one slot
        cls.template = ItemTemplateFactory(
            facet_capacity=1,
            gear_archetype=GearArchetype.HEAVY_ARMOR,
        )
        TemplateSlotFactory(
            template=cls.template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )

        # 6. One ItemInstance bearing the facet, equipped on the character
        cls.instance = ItemInstanceFactory(template=cls.template, quality_tier=cls.item_quality)
        cls.item_facet = ItemFacetFactory(
            item_instance=cls.instance,
            facet=cls.facet,
            attachment_quality_tier=cls.attach_quality,
        )
        EquippedItemFactory(
            character=cls.character_obj,
            item_instance=cls.instance,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )

        # 7. FACET-kind thread anchored to the facet, level=1
        cls.thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            target_kind=TargetKind.FACET,
            target_facet=cls.facet,
            target_trait=None,
            level=1,
        )

        # 8. Tier-0 FLAT_BONUS ThreadPullEffect for this resonance
        cls.effect = ThreadPullEffectFactory(
            target_kind=TargetKind.FACET,
            resonance=cls.resonance,
            tier=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=5,
        )

        # 9. Covenant role assigned to the character — engaged so covenant_role_bonus fires
        from world.covenants.services import set_engaged_membership

        cls.assignment = CharacterCovenantRoleFactory(character_sheet=cls.sheet)
        set_engaged_membership(membership=cls.assignment)

        # 10. GearArchetypeCompatibility for (role, HEAVY_ARMOR) — compatible pair
        GearArchetypeCompatibilityFactory(
            covenant_role=cls.assignment.covenant_role,
            gear_archetype=GearArchetype.HEAVY_ARMOR,
        )

        # 11. Invalidate handler caches so fresh load sees all rows
        cls.character_obj.equipped_items.invalidate()
        cls.character_obj.covenant_roles.invalidate()

    def test_query_budget_after_handler_warm(self) -> None:
        """Pin get_modifier_total to BASELINE_QUERIES after character-side handlers are warm.

        Documented query budget (9 total on first call):
          Query 1: CharacterModifier.exists() — always fires in get_modifier_breakdown,
                   returns early because no CharacterModifier rows exist for this sheet.
          Query 2: ThreadPullEffect.filter(target_kind=FACET, resonance=..., tier=0, ...) —
                   _thread_pull_effects_for always queries the DB; SharedMemoryModel
                   identity-map caches model instances by PK, not arbitrary filter results.
          Query 3: CharacterClassLevel select_related — CharacterSheet.current_level is a
                   @cached_property read by covenant_role_bonus → role_base_bonus_for_target.
                   Fires once per sheet instance; cached after the first call.
          Query 4: GearArchetypeCompatibility.filter(...).exists() — is_gear_compatible
                   queries the DB once per unique (role, archetype) pair encountered
                   during the equipped-items walk.
          Query 5: CovenantLevelBonus.filter(modifier_target=...).first() —
                   covenant_level_bonus (#762) fires once per engaged member's
                   modifier-total call; returns None here (no authored row for this
                   target) so it contributes 0 to the result.
          Query 6: CharacterSheet.motif reverse-OneToOne fetch —
                   passive_motif_style_bonuses (#1150) resolves the character's Motif
                   for the resonance-linked target. The reverse OneToOne is keyed on
                   character_id, not PK, so the SharedMemoryModel identity map can't
                   serve it; one query fires. This character has no Motif, so it raises
                   DoesNotExist and contributes 0 to the result.
          Query 7: CovenantRoleBonus.filter(covenant_role=..., modifier_target=...).first() —
                   role_base_bonus_for_target (#985) fires once per engaged role's
                   modifier-total call; returns None here (no authored row for this
                   target) so it contributes 0. Parallel to Query 5's CovenantLevelBonus
                   lookup.
          Query 8: CrossingChoice.filter(thread=...) — passive_facet_crossing_bonuses
                   (#1990) fires once per FACET-kind thread; returns no rows (no crossing
                   choices authored) so it contributes 0 to the result.
          Query 9: VowStatScaling.filter(covenant_role__in=..., modifier_target=...) —
                   vow_stat_scaling_bonus (#2022) fires once per engaged role's
                   modifier-total call; returns no rows (no authored scaling) so it
                   contributes 0.

        Note: the former Query 10 (the "gear scaling" archetype-keyed multiplier lookup,
        #2022) was removed by the #2529 short-circuit (CovenantRole.archetype was removed
        for the SWORD/SHIELD/CROWN blend rewrite) and the underlying model + consumer were
        fully removed by #2533 (replaced by the defense-profile gear-substitution fraction
        at the armor-soak seam, ``world.covenants.services.gear_additive_fraction``).

        Queries that do NOT fire after warming:
          - equipped_items queryset (warmed by iter_item_facets)
          - threads queryset (warmed by threads_of_kind)
          - covenant_roles queryset (warmed by currently_engaged_roles)
          - quality_tier FK walk (identity-mapped after first access in setUpTestData)
          - item template FK walk (identity-mapped)

        If this count increases, a new DB query was introduced in the equipment walk.
        Investigate the diff in world/mechanics/services.py or world/covenants/services.py.
        """
        from world.magic.constants import TargetKind
        from world.mechanics.services import get_modifier_total

        # --- Warm all character-side handler caches ---
        # equipped_items handler: loads EquippedItem rows + item facets into memory
        list(self.character_obj.equipped_items.iter_item_facets())
        # threads handler: loads Thread rows into memory
        list(self.character_obj.threads.threads_of_kind(TargetKind.FACET))
        # covenant_roles handler: loads CharacterCovenantRole rows into memory
        list(self.character_obj.covenant_roles.currently_engaged_roles())

        # --- Assert documented query count ---
        # BASELINE = 9: CharacterModifier.exists + ThreadPullEffect.filter
        #               + CharacterClassLevel (current_level) + is_gear_compatible
        #               + CovenantLevelBonus.first() (covenant_level_bonus, #762)
        #               + CharacterSheet.motif fetch (passive_motif_style_bonuses, #1150)
        #               + CovenantRoleBonus.first() (role_base_bonus_for_target, #985)
        #               + CrossingChoice.filter (passive_facet_crossing_bonuses, #1990)
        #               + VowStatScaling.filter (vow_stat_scaling_bonus, #2022)
        # (the "gear scaling" query, #2022, was removed by the #2529 short-circuit and
        # the underlying model + consumer were fully removed by #2533 — see the
        # docstring note above.)
        baseline_queries = 9
        with self.assertNumQueries(baseline_queries):
            result = get_modifier_total(self.sheet, self.target)

        # Sanity-check: result should be non-zero (facet bonus path actually fired)
        # flat_bonus=5, item_mult=1.0, attach_mult=1.0, level=max(1,1)=1 → 5
        # covenant role path: role_base_bonus_for_target returns 0 (PR1 placeholder) →
        # max(0, 0) = 0 (since item_mundane_stat_for_target also returns 0)
        # Total: 5 (facet) + 0 (covenant) = 5
        self.assertEqual(result, 5)

    def test_no_handler_warm_query_count_is_higher(self) -> None:
        """Without warming, handler queries fire on top of the baseline 9.

        This is the control test: demonstrate that warmup matters. After
        invalidating the handler caches, we expect MORE than 9 queries because
        the handler walks (equipped_items, threads, covenant_roles) must fetch
        from the DB on first access.

        We assert > baseline_queries rather than pinning an exact count, since
        the handler query count may evolve with handler implementation changes.
        This test ensures test_query_budget_after_handler_warm is not trivially
        passing because the function does nothing.
        """
        from world.magic.constants import TargetKind
        from world.mechanics.services import get_modifier_total

        # Invalidate all handler caches to force DB queries on next access
        self.character_obj.equipped_items.invalidate()
        self.character_obj.threads.invalidate()
        self.character_obj.covenant_roles.invalidate()

        baseline_queries = 9

        # Capture actual count by running without constraint
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as ctx:
            get_modifier_total(self.sheet, self.target)
        actual_count = len(ctx)

        self.assertGreater(
            actual_count,
            baseline_queries,
            f"Expected handler-cold call to fire more than {baseline_queries} queries, "
            f"but only fired {actual_count}. Either the handlers don't query the DB "
            f"(unexpected) or the baseline is wrong.",
        )

        # Re-warm so later tests are unaffected (setUpTestData rolls back writes
        # but handler state is in-process; invalidate was mutating)
        list(self.character_obj.equipped_items.iter_item_facets())
        list(self.character_obj.threads.threads_of_kind(TargetKind.FACET))
        list(self.character_obj.covenant_roles.currently_engaged_roles())


class CovenantRoleAnchorCapQueryBudgetTests(TestCase):
    """Query-budget guard for the COVENANT_ROLE anchor cap (Slice G / #517).

    The covenant and tenure components must read the warmed
    CharacterCovenantRoleHandler cache with ZERO queries (the _rows
    select_related("covenant") requirement — max_covenant_level_for_role and
    days_held_in_role walk the cache, never re-fetching covenant rows). The
    legend component (get_character_role_legend) is a derive-on-read lookup
    against CovenantLegendCredit and costs exactly one query; covenant
    membership is supplied from the cache (covenant_ids_for_role), so the cap
    does NOT re-query the role's covenants.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        from world.covenants.factories import make_engaged_member
        from world.magic.constants import TargetKind
        from world.magic.factories import ThreadFactory

        cls.membership = make_engaged_member()
        cls.thread = ThreadFactory(
            owner=cls.membership.character_sheet,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=cls.membership.covenant_role,
            target_trait=None,
        )

    def test_covenant_and_tenure_components_zero_queries(self) -> None:
        """Covenant level, tenure, and covenant-id lookups walk the cache — no queries."""
        handler = self.membership.character_sheet.character.covenant_roles
        role = self.membership.covenant_role
        list(handler.currently_engaged_roles())  # warm
        with self.assertNumQueries(0):
            handler.max_covenant_level_for_role(role)
            handler.days_held_in_role(role)
            handler.covenant_ids_for_role(role)

    def test_compute_anchor_cap_covenant_role_single_legend_query(self) -> None:
        """The whole cap fires exactly one query: the legend-credit lookup.

        Covenant + tenure components are cache-only and covenant_ids come from the
        warmed handler, so the only DB hit is the CovenantLegendCredit query.
        """
        from world.magic.services.threads import compute_anchor_cap

        list(self.membership.character_sheet.character.covenant_roles.currently_engaged_roles())
        with self.assertNumQueries(1):
            compute_anchor_cap(self.thread)
