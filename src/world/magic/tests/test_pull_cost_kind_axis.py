"""Tests for the per-target-kind pull cost axis (ADR-0051).

Covers:
- pull cost is uniform across thread kinds (no penalty for gift/strength; #1581)
- imbue dp multiplier: GIFT threads cost more to imbue than non-GIFT
"""

from __future__ import annotations

from django.test import TestCase

from world.magic.constants import TargetKind
from world.magic.factories import (
    CharacterResonanceFactory,
    CharacterSheetFactory,
    GiftFactory,
    ResonanceFactory,
    ThreadFactory,
    ThreadPullCostFactory,
)
from world.magic.services.resonance import spend_resonance_for_imbuing
from world.magic.services.threads import get_imbue_cost_multiplier
from world.seeds.game_content.magic import seed_thread_pull_catalog


class PullCostUniformAcrossKindsTests(TestCase):
    """#1581: pulling a thread costs the same regardless of its kind — no
    penalty for a stronger (gift) anchor. Only IMBUE cost may differ."""

    @classmethod
    def setUpTestData(cls):
        seed_thread_pull_catalog()  # seeds universal rows + the gift imbue row

    def test_gift_pull_cost_equals_universal(self):
        from world.magic.constants import TargetKind
        from world.magic.services.threads import get_pull_cost

        universal = get_pull_cost(1, None)
        gift = get_pull_cost(1, TargetKind.GIFT)
        self.assertEqual(gift.resonance_cost, universal.resonance_cost)
        self.assertEqual(gift.anima_per_thread, universal.anima_per_thread)


class ImbueCostMultiplierTests(TestCase):
    """GIFT threads cost more dp to imbue than non-GIFT threads (ADR-0051)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.universal_t1 = ThreadPullCostFactory(
            tier=1, target_kind=None, resonance_cost=1, anima_per_thread=1, label="soft"
        )
        cls.gift_t1 = ThreadPullCostFactory(
            tier=1,
            target_kind=TargetKind.GIFT,
            resonance_cost=2,
            anima_per_thread=2,
            imbue_cost_multiplier=2,
            label="gift-soft",
        )
        cls.resonance = ResonanceFactory()
        cls.sheet = CharacterSheetFactory()
        cls.gift = GiftFactory()
        CharacterResonanceFactory(character_sheet=cls.sheet, resonance=cls.resonance, balance=1000)

    def test_get_imbue_cost_multiplier_gift(self) -> None:
        """GIFT kind resolves multiplier=2 from the GIFT-specific cost row."""
        self.assertEqual(get_imbue_cost_multiplier(TargetKind.GIFT), 2)

    def test_get_imbue_cost_multiplier_universal(self) -> None:
        """Non-GIFT kinds resolve multiplier=1 from the universal row."""
        self.assertEqual(get_imbue_cost_multiplier(TargetKind.TRAIT), 1)
        self.assertEqual(get_imbue_cost_multiplier(None), 1)

    def test_gift_thread_costs_more_dp_to_imbue(self) -> None:
        """At the same level, a GIFT thread costs 2x the dp of a TRAIT thread.

        Both threads start at level 0, below the cost curve's start level, so a step costs
        the base cost's tenth: 10 dp. GIFT multiplier 2 makes each level cost 20 dp; TRAIT
        multiplier 1 keeps each level at 10 dp. We imbue enough to advance one level and
        compare the developed_points consumed.
        """
        # TRAIT thread: needs a trait value >= 1 so anchor cap > 0.
        from world.traits.factories import CharacterTraitValueFactory

        trait_thread = ThreadFactory(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.TRAIT,
            level=0,
            developed_points=0,
        )
        CharacterTraitValueFactory(
            character=self.sheet,
            trait=trait_thread.target_trait,
            value=50,
        )

        gift_thread = ThreadFactory(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
            target_trait=None,
            level=0,
            developed_points=0,
        )

        # GIFT: 20 dp to advance 0→1 (10 base × 2 multiplier).
        gift_result = spend_resonance_for_imbuing(
            character_sheet=self.sheet,
            thread=gift_thread,
            resonance=gift_thread.resonance,
            amount=20,
        )
        self.assertEqual(gift_thread.level, 1)
        self.assertEqual(gift_result.levels_gained, 1)

        # TRAIT: 10 dp to advance 0→1 (10 base × 1 multiplier).
        trait_result = spend_resonance_for_imbuing(
            character_sheet=self.sheet,
            thread=trait_thread,
            resonance=trait_thread.resonance,
            amount=10,
        )
        self.assertEqual(trait_thread.level, 1)
        self.assertEqual(trait_result.levels_gained, 1)

        # The GIFT thread needed more dp to cross the same level boundary.
        self.assertGreater(gift_result.developed_points_added, trait_result.developed_points_added)


class UnauthoredPullTierTests(TestCase):
    """A tier staff have not authored a cost row for is refused with one sentence."""

    SENTENCE = "That pull tier is not available yet."

    @classmethod
    def setUpTestData(cls) -> None:
        ThreadPullCostFactory(tier=1, target_kind=None, resonance_cost=1, anima_per_thread=0)
        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=cls.sheet, resonance=cls.resonance, balance=20, lifetime_earned=20
        )
        cls.thread = ThreadFactory(owner=cls.sheet, resonance=cls.resonance, level=1)

    def test_the_cost_resolver_refuses_in_a_player_sentence(self) -> None:
        from world.magic.exceptions import InvalidImbueAmount, PullTierNotAvailable
        from world.magic.services.threads import get_pull_cost

        with self.assertRaises(PullTierNotAvailable) as raised:
            get_pull_cost(2, None)

        self.assertEqual(raised.exception.user_message, self.SENTENCE)
        self.assertIsInstance(raised.exception, InvalidImbueAmount)

    def test_committing_a_pull_at_the_tier_refuses_and_charges_nothing(self) -> None:
        from world.magic.exceptions import PullTierNotAvailable
        from world.magic.models import CharacterResonance
        from world.magic.services.resonance import spend_resonance_for_pull
        from world.magic.types import PullActionContext

        with self.assertRaises(PullTierNotAvailable):
            spend_resonance_for_pull(
                character_sheet=self.sheet,
                threads=[self.thread],
                tier=2,
                action_context=PullActionContext(),
            )

        row = CharacterResonance.objects.get(character_sheet=self.sheet, resonance=self.resonance)
        self.assertEqual(row.balance, 20)

    def test_declaring_a_cast_pull_at_the_tier_refuses(self) -> None:
        from world.combat.pull_helpers import build_cast_pull_declaration
        from world.magic.exceptions import PullTierNotAvailable

        with self.assertRaises(PullTierNotAvailable):
            build_cast_pull_declaration(self.sheet.pk, tier=2, thread_ids=[self.thread.pk])

    def test_the_imbue_multiplier_still_defaults_to_one_with_no_row(self) -> None:
        self.assertEqual(get_imbue_cost_multiplier(TargetKind.GIFT), 1)
