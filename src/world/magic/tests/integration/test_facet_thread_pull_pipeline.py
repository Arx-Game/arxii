"""End-to-end integration tests for Spec D — facet thread pull pipeline.

Pipeline: build sheet + FACET Thread + equipped item bearing the Facet →
call spend_resonance_for_pull → assert CombatPull + CombatPullResolvedEffect
rows are written with FACET-aware scaled values.

Math reference (happy path):
  item_quality.stat_multiplier = 2.00
  attachment_quality.stat_multiplier = 3.00
  worn_aggregate = 2.00 × 3.00 = 6.00
  thread.level = 2 → level_multiplier = max(1, 2//10) = 1

  tier-0 effect: authored=5, scaled = int(5 × 1 × 6.0) = 30
  tier-1 effect: authored=10, scaled = int(10 × 1 × 6.0) = 60
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.models import CombatPull, CombatPullResolvedEffect
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import (
    EquippedItemFactory,
    ItemFacetFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
    QualityTierFactory,
    TemplateSlotFactory,
)
from world.magic.constants import EffectKind, TargetKind
from world.magic.exceptions import NoMatchingWornFacetItemsError
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterResonanceFactory,
    FacetFactory,
    ResonanceFactory,
    ThreadPullCostFactory,
    ThreadPullEffectFactory,
)
from world.magic.models import CharacterResonance, Thread
from world.magic.services import spend_resonance_for_pull
from world.magic.types import PullActionContext


class FacetThreadPullCombatTests(TestCase):
    """Happy path: FACET thread + equipped matching item → CombatPull + ResolvedEffect rows.

    Uses setUpTestData for fixture creation; each test method re-fetches
    CharacterResonance from DB to confirm balance changes.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        # 1. CharacterSheet backed by a real RosterTenure (required for CharacterAnima lookup
        #    and to satisfy is_protagonism_locked).
        cls.sheet = CharacterSheetFactory()

        # 2. Facet, Resonance.
        cls.facet = FacetFactory(name="FacetPullPipeFacet")
        cls.resonance = ResonanceFactory()

        # 3. CharacterResonance with sufficient balance.
        CharacterResonanceFactory(
            character_sheet=cls.sheet,
            resonance=cls.resonance,
            balance=20,
            lifetime_earned=20,
        )

        # 4. CharacterAnima with sufficient current (anima_per_thread=0 for tier-1, so
        #    even current=0 would pass; use 5 for clarity).
        CharacterAnimaFactory(character=cls.sheet.character, current=5, maximum=10)

        # 5. ThreadPullCost row for tier=1.
        cls.cost = ThreadPullCostFactory(
            tier=1,
            resonance_cost=2,
            anima_per_thread=0,
        )

        # 6. Thread on FACET kind, level=2.
        cls.thread = Thread.objects.create(
            owner=cls.sheet,
            resonance=cls.resonance,
            target_kind=TargetKind.FACET,
            target_facet=cls.facet,
            level=2,
            developed_points=0,
        )

        # 7. Quality tiers.
        cls.item_quality = QualityTierFactory(
            name="FacetPullPipeItemQ", stat_multiplier=Decimal("2.00")
        )
        cls.attach_quality = QualityTierFactory(
            name="FacetPullPipeAttachQ", stat_multiplier=Decimal("3.00")
        )

        # 8. ItemTemplate with a TemplateSlot, ItemInstance equipped, ItemFacet attached.
        cls.template = ItemTemplateFactory(facet_capacity=1)
        TemplateSlotFactory(
            template=cls.template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        cls.instance = ItemInstanceFactory(
            template=cls.template,
            quality_tier=cls.item_quality,
        )
        EquippedItemFactory(
            character=cls.sheet.character,
            item_instance=cls.instance,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        cls.item_facet = ItemFacetFactory(
            item_instance=cls.instance,
            facet=cls.facet,
            attachment_quality_tier=cls.attach_quality,
        )

        # 9. Tier-0 FLAT_BONUS ThreadPullEffect (always-on passive pulled into the envelope).
        ThreadPullEffectFactory(
            target_kind=TargetKind.FACET,
            resonance=cls.resonance,
            tier=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=5,
        )

        # 10. Tier-1 FLAT_BONUS ThreadPullEffect (paid pull).
        ThreadPullEffectFactory(
            target_kind=TargetKind.FACET,
            resonance=cls.resonance,
            tier=1,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=10,
        )

        # 11. CombatEncounter + CombatParticipant.
        cls.encounter = CombatEncounterFactory(round_number=1)
        cls.participant = CombatParticipantFactory(
            encounter=cls.encounter,
            character_sheet=cls.sheet,
        )

        # 12. PullActionContext.
        #     FACET threads are _ALWAYS_IN_ACTION_KINDS, so involved_* tuples can be empty.
        cls.ctx = PullActionContext(
            combat_encounter=cls.encounter,
            participant=cls.participant,
        )

        # Invalidate handler cache so it sees the newly equipped item.
        cls.sheet.character.equipped_items.invalidate()

    def test_combat_pull_writes_resolved_effects_with_facet_scaling(self) -> None:
        """Happy path: FACET pull in combat → CombatPull + CombatPullResolvedEffect written.

        Math:
          worn_aggregate = item_quality(2.0) × attach_quality(3.0) = 6.0
          level_multiplier = max(1, 2//10) = 1
          tier-0 effect: int(5 × 1 × 6.0) = 30
          tier-1 effect: int(10 × 1 × 6.0) = 60
        """
        pre_balance = CharacterResonance.objects.get(
            character_sheet=self.sheet,
            resonance=self.resonance,
        ).balance
        pre_pull_count = CombatPull.objects.count()

        result = spend_resonance_for_pull(
            self.sheet,
            self.resonance,
            tier=1,
            threads=[self.thread],
            action_context=self.ctx,
        )

        # Resonance spent matches cost row.
        self.assertEqual(result.resonance_spent, self.cost.resonance_cost)

        # Single thread with anima_per_thread=0: no anima deducted.
        self.assertEqual(result.anima_spent, 0)

        # A CombatPull row was created.
        self.assertEqual(CombatPull.objects.count() - pre_pull_count, 1)
        pull = CombatPull.objects.get(
            participant=self.participant,
            round_number=self.encounter.round_number,
        )
        self.assertIsNotNone(pull)

        # Two authored effects (tier-0 + tier-1) → two frozen rows.
        resolved_db = CombatPullResolvedEffect.objects.filter(pull=pull)
        self.assertEqual(resolved_db.count(), 2)

        # Verify exact scaled_value for each tier.
        tier0_row = resolved_db.get(source_tier=0)
        self.assertEqual(tier0_row.authored_value, 5)
        self.assertEqual(tier0_row.level_multiplier, 1)
        self.assertEqual(tier0_row.scaled_value, 30)

        tier1_row = resolved_db.get(source_tier=1)
        self.assertEqual(tier1_row.authored_value, 10)
        self.assertEqual(tier1_row.level_multiplier, 1)
        self.assertEqual(tier1_row.scaled_value, 60)

        # Balance decreased by the resonance cost.
        post_cr = CharacterResonance.objects.get(
            character_sheet=self.sheet,
            resonance=self.resonance,
        )
        self.assertEqual(post_cr.balance, pre_balance - self.cost.resonance_cost)

        # In-memory resolved effects also carry correct scaled values.
        scaled_values = sorted(
            r.scaled_value for r in result.resolved_effects if r.scaled_value is not None
        )
        self.assertEqual(scaled_values, [30, 60])


class FacetThreadPullNoItemTests(TestCase):
    """Failure path: FACET thread with no matching worn item → NoMatchingWornFacetItemsError."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.facet = FacetFactory(name="FacetPullNoItemFacet")
        cls.resonance = ResonanceFactory()

        CharacterResonanceFactory(
            character_sheet=cls.sheet,
            resonance=cls.resonance,
            balance=20,
            lifetime_earned=20,
        )
        CharacterAnimaFactory(character=cls.sheet.character, current=5, maximum=10)
        ThreadPullCostFactory(tier=1, resonance_cost=2, anima_per_thread=0)

        cls.thread = Thread.objects.create(
            owner=cls.sheet,
            resonance=cls.resonance,
            target_kind=TargetKind.FACET,
            target_facet=cls.facet,
            level=2,
            developed_points=0,
        )

        ThreadPullEffectFactory(
            target_kind=TargetKind.FACET,
            resonance=cls.resonance,
            tier=1,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=10,
        )

        cls.encounter = CombatEncounterFactory(round_number=1)
        cls.participant = CombatParticipantFactory(
            encounter=cls.encounter,
            character_sheet=cls.sheet,
        )
        cls.ctx = PullActionContext(
            combat_encounter=cls.encounter,
            participant=cls.participant,
        )

        # No item equipped — the worn-items gate should fire.
        cls.sheet.character.equipped_items.invalidate()

    def test_no_matching_item_raises_and_preserves_balance(self) -> None:
        """No worn item for the facet → NoMatchingWornFacetItemsError; balance unchanged."""
        pre_balance = CharacterResonance.objects.get(
            character_sheet=self.sheet,
            resonance=self.resonance,
        ).balance
        pre_pull_count = CombatPull.objects.count()

        with self.assertRaises(NoMatchingWornFacetItemsError):
            spend_resonance_for_pull(
                self.sheet,
                self.resonance,
                tier=1,
                threads=[self.thread],
                action_context=self.ctx,
            )

        # Balance must be untouched.
        post_cr = CharacterResonance.objects.get(
            character_sheet=self.sheet,
            resonance=self.resonance,
        )
        self.assertEqual(post_cr.balance, pre_balance)

        # No CombatPull row was written.
        self.assertEqual(CombatPull.objects.count(), pre_pull_count)
