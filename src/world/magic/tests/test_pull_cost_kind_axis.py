"""Tests for the per-target-kind pull cost axis (ADR-0051).

Covers:
- ThreadPullCost.target_kind + imbue_cost_multiplier schema
- get_pull_cost resolver (universal, kind-specific, fallback, invalid input)
- resolve_pull_cost_for_threads (max-cost rule for mixed-kind pulls)
- spend_resonance_for_pull charges the GIFT rate for GIFT threads
- preview_resonance_pull mirrors the spend assertions
- imbue dp multiplier: GIFT threads cost more to imbue than non-GIFT
"""

from __future__ import annotations

from django.test import TestCase

from world.magic.constants import TargetKind
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterResonanceFactory,
    CharacterSheetFactory,
    GiftFactory,
    ResonanceFactory,
    ThreadFactory,
    ThreadPullCostFactory,
    ThreadPullEffectFactory,
)
from world.magic.models import CharacterResonance, Thread
from world.magic.services.resonance import (
    preview_resonance_pull,
    spend_resonance_for_imbuing,
    spend_resonance_for_pull,
)
from world.magic.services.threads import (
    get_imbue_cost_multiplier,
    get_pull_cost,
    resolve_pull_cost_for_threads,
)
from world.magic.types import PullActionContext


class GetPullCostResolverTests(TestCase):
    """get_pull_cost: kind-specific → universal fallback."""

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

    def test_kind_specific_row_preferred(self) -> None:
        """A kind-specific row is returned when it exists."""
        cost = get_pull_cost(1, TargetKind.GIFT)
        self.assertEqual(cost.pk, self.gift_t1.pk)
        self.assertEqual(cost.resonance_cost, 2)

    def test_universal_fallback_when_no_kind_specific(self) -> None:
        """Falls back to the universal row when no kind-specific row exists."""
        cost = get_pull_cost(1, TargetKind.TRAIT)
        self.assertEqual(cost.pk, self.universal_t1.pk)
        self.assertEqual(cost.resonance_cost, 1)

    def test_universal_when_target_kind_none(self) -> None:
        """target_kind=None resolves to the universal row."""
        cost = get_pull_cost(1, None)
        self.assertEqual(cost.pk, self.universal_t1.pk)

    def test_invalid_target_kind_raises(self) -> None:
        """An invalid target_kind string raises ValueError (fail fast)."""
        with self.assertRaises(ValueError):
            get_pull_cost(1, "NOT_A_REAL_KIND")


class ResolvePullCostForThreadsTests(TestCase):
    """resolve_pull_cost_for_threads: max-cost rule for mixed-kind pulls."""

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
            label="gift-soft",
        )
        cls.resonance = ResonanceFactory()
        cls.sheet = CharacterSheetFactory()
        cls.gift = GiftFactory()

    def _make_gift_thread(self) -> Thread:
        return ThreadFactory(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
            target_trait=None,
        )

    def _make_trait_thread(self) -> Thread:
        return ThreadFactory(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.TRAIT,
        )

    def test_single_gift_thread_uses_gift_cost(self) -> None:
        """A GIFT-only pull uses the GIFT cost row."""
        threads = [self._make_gift_thread()]
        cost = resolve_pull_cost_for_threads(1, threads)
        self.assertEqual(cost.pk, self.gift_t1.pk)

    def test_single_trait_thread_uses_universal_cost(self) -> None:
        """A TRAIT-only pull uses the universal cost row."""
        threads = [self._make_trait_thread()]
        cost = resolve_pull_cost_for_threads(1, threads)
        self.assertEqual(cost.pk, self.universal_t1.pk)

    def test_mixed_kind_uses_max_cost(self) -> None:
        """A mixed GIFT+TRAIT pull charges the GIFT rate (costliest)."""
        gift_thread = self._make_gift_thread()
        trait_thread = self._make_trait_thread()
        # GIFT thread is second in the list — max-cost must still win.
        cost = resolve_pull_cost_for_threads(1, [trait_thread, gift_thread])
        self.assertEqual(cost.pk, self.gift_t1.pk)
        self.assertEqual(cost.resonance_cost, 2)

    def test_mixed_kind_order_independent(self) -> None:
        """Max-cost is deterministic regardless of thread ordering."""
        gift_thread = self._make_gift_thread()
        trait_thread = self._make_trait_thread()
        cost_a = resolve_pull_cost_for_threads(1, [gift_thread, trait_thread])
        cost_b = resolve_pull_cost_for_threads(1, [trait_thread, gift_thread])
        self.assertEqual(cost_a.pk, cost_b.pk)
        self.assertEqual(cost_a.pk, self.gift_t1.pk)


class SpendResonanceForPullKindAxisTests(TestCase):
    """spend_resonance_for_pull charges the kind-specific rate."""

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
        CharacterAnimaFactory(character=cls.sheet.character, current=100, maximum=100)
        CharacterResonanceFactory(character_sheet=cls.sheet, resonance=cls.resonance, balance=100)
        # Effect rows so the pull resolves at least one applicable effect
        # (target_kind matches the thread's discriminator).
        ThreadPullEffectFactory(
            target_kind=TargetKind.GIFT,
            resonance=cls.resonance,
            tier=1,
            flat_bonus_amount=1,
        )
        ThreadPullEffectFactory(
            target_kind=TargetKind.TRAIT,
            resonance=cls.resonance,
            tier=1,
            flat_bonus_amount=1,
        )

    def _make_gift_thread(self) -> Thread:
        return ThreadFactory(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
            target_trait=None,
        )

    def _make_trait_thread(self) -> Thread:
        return ThreadFactory(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.TRAIT,
        )

    def test_gift_pull_debits_more_than_trait_pull(self) -> None:
        """A GIFT-thread pull debits more resonance than a TRAIT-thread pull."""
        # GIFT thread — always in-action, no context needed.
        gift_thread = self._make_gift_thread()
        cr_gift = CharacterResonance.objects.get(
            character_sheet=self.sheet, resonance=self.resonance
        )
        cr_gift.balance = 100
        cr_gift.save(update_fields=["balance"])
        anima = self.sheet.character.anima
        anima.current = 100
        anima.save(update_fields=["current"])

        ctx = PullActionContext()
        result_gift = spend_resonance_for_pull(
            character_sheet=self.sheet,
            resonance=self.resonance,
            tier=1,
            threads=[gift_thread],
            action_context=ctx,
        )
        self.assertEqual(result_gift.resonance_spent, 2)

        # TRAIT thread — needs involved_traits in the context.
        trait_thread = self._make_trait_thread()
        cr_trait = CharacterResonance.objects.get(
            character_sheet=self.sheet, resonance=self.resonance
        )
        cr_trait.balance = 100
        cr_trait.save(update_fields=["balance"])
        anima = self.sheet.character.anima
        anima.current = 100
        anima.save(update_fields=["current"])

        ctx = PullActionContext(involved_traits=(trait_thread.target_trait_id,))
        result_trait = spend_resonance_for_pull(
            character_sheet=self.sheet,
            resonance=self.resonance,
            tier=1,
            threads=[trait_thread],
            action_context=ctx,
        )
        self.assertEqual(result_trait.resonance_spent, 1)

        self.assertGreater(result_gift.resonance_spent, result_trait.resonance_spent)


class PreviewResonancePullKindAxisTests(TestCase):
    """preview_resonance_pull mirrors the spend cost assertions (no debit)."""

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
            label="gift-soft",
        )
        cls.resonance = ResonanceFactory()
        cls.sheet = CharacterSheetFactory()
        cls.gift = GiftFactory()
        CharacterAnimaFactory(character=cls.sheet.character, current=100, maximum=100)
        CharacterResonanceFactory(character_sheet=cls.sheet, resonance=cls.resonance, balance=100)
        # Effect rows so the preview resolves effects (cosmetic for cost test).
        ThreadPullEffectFactory(
            target_kind=TargetKind.GIFT,
            resonance=cls.resonance,
            tier=1,
            flat_bonus_amount=1,
        )
        ThreadPullEffectFactory(
            target_kind=TargetKind.TRAIT,
            resonance=cls.resonance,
            tier=1,
            flat_bonus_amount=1,
        )

    def _make_gift_thread(self) -> Thread:
        return ThreadFactory(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
            target_trait=None,
        )

    def _make_trait_thread(self) -> Thread:
        return ThreadFactory(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.TRAIT,
        )

    def test_gift_preview_shows_higher_cost(self) -> None:
        """The GIFT preview shows resonance_cost=2 vs the TRAIT preview's 1."""
        gift_thread = self._make_gift_thread()
        gift_preview = preview_resonance_pull(
            character_sheet=self.sheet,
            resonance=self.resonance,
            tier=1,
            threads=[gift_thread],
        )
        self.assertEqual(gift_preview.resonance_cost, 2)

        trait_thread = self._make_trait_thread()
        trait_preview = preview_resonance_pull(
            character_sheet=self.sheet,
            resonance=self.resonance,
            tier=1,
            threads=[trait_thread],
        )
        self.assertEqual(trait_preview.resonance_cost, 1)


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

        Both threads start at level 0. Sub-10 levels each cost max((n-9)*100, 1) = 1 dp
        base. GIFT multiplier 2 makes each level cost 2 dp; TRAIT multiplier 1 keeps
        each level at 1 dp. We imbue enough to advance one level and compare the
        developed_points consumed.
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
            character=self.sheet.character,
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

        # GIFT: 2 dp to advance 0→1 (1 base × 2 multiplier).
        gift_result = spend_resonance_for_imbuing(
            character_sheet=self.sheet, thread=gift_thread, amount=2
        )
        self.assertEqual(gift_thread.level, 1)
        self.assertEqual(gift_result.levels_gained, 1)

        # TRAIT: 1 dp to advance 0→1 (1 base × 1 multiplier).
        trait_result = spend_resonance_for_imbuing(
            character_sheet=self.sheet, thread=trait_thread, amount=1
        )
        self.assertEqual(trait_thread.level, 1)
        self.assertEqual(trait_result.levels_gained, 1)

        # The GIFT thread needed more dp to cross the same level boundary.
        self.assertGreater(gift_result.developed_points_added, trait_result.developed_points_added)
