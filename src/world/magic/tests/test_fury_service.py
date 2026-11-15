"""Tests for the fury resolution service (strength cap, clamp, the bought share)."""

from decimal import Decimal

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.services.encounter.config import get_strain_config
from world.magic.factories import (
    FuryConfigFactory,
    FuryDegreeShareFactory,
    FuryTierFactory,
    KindledStrengthTierFactory,
    ResonanceFactory,
    kindle_resonance,
)
from world.magic.services.fury import (
    clamp_tier,
    give_in_refusal,
    give_in_strength,
    provocation_cap,
    provocation_ease,
    resolve_fury,
)
from world.traits.factories import CheckOutcomeFactory, ensure_level_ladder


class ClampTierTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        FuryConfigFactory()
        cls.t1 = FuryTierFactory(name="Smouldering", depth=1, control_surrendered=2)
        cls.t3 = FuryTierFactory(name="Berserk", depth=3, control_surrendered=8, berserk_severity=5)

    def test_clamp_drops_tier_above_cap(self):
        self.assertEqual(clamp_tier(self.t3, cap=1), self.t1)

    def test_clamp_returns_none_when_cap_zero(self):
        self.assertIsNone(clamp_tier(self.t1, cap=0))


class ResolveFuryNoResonanceTests(TestCase):
    """No resonance named (real character, resonance=None) → fury unavailable."""

    @classmethod
    def setUpTestData(cls):
        FuryConfigFactory()
        cls.t1 = FuryTierFactory(name="Smouldering", depth=1, control_surrendered=2)
        cls.character = CharacterSheetFactory()

    def test_no_resonance_returns_unavailable(self):
        """resonance=None → cap=0 → clamp returns None → nothing surrendered or bought."""
        res = resolve_fury(
            tier=self.t1,
            strength=give_in_strength(self.character, None),
            check_result=_FakeCheck(CheckOutcomeFactory(name="Success", success_level=1)),
        )
        self.assertIsNone(res.realized_tier)
        self.assertEqual(res.control_surrendered, 0)
        self.assertEqual(res.intensity_gained, 0)
        self.assertEqual(res.berserk_severity, 0)


class ResolveFuryStrengthTests(TestCase):
    """resolve_fury with a strength row: cap → clamp → the share the outcome buys.

    The strongest strength row caps depth at 2 and grows the trade by 20%. 1.50 intensity per
    control surrendered. Smouldering surrenders 10: full trade 10 x 1.5 x 1.2 = 18.
    """

    @classmethod
    def setUpTestData(cls):
        FuryConfigFactory()
        cls.strength = KindledStrengthTierFactory(
            rank=3, give_in_max_depth=2, give_in_bonus_percent=20, give_in_ease_tenths=8
        )
        config = get_strain_config()
        config.intensity_per_control_surrendered = Decimal("1.50")
        config.save()
        cls.partial = CheckOutcomeFactory(name="Partial", success_level=0)
        cls.success = CheckOutcomeFactory(name="Success", success_level=1)
        cls.unshared = CheckOutcomeFactory(name="Failure", success_level=-1)
        FuryDegreeShareFactory(outcome_tier=cls.partial, intensity_percent=50)
        FuryDegreeShareFactory(outcome_tier=cls.success, intensity_percent=100)
        cls.t1 = FuryTierFactory(name="Smouldering", depth=1, control_surrendered=10)
        cls.t3 = FuryTierFactory(
            name="Infernal", depth=3, control_surrendered=20, berserk_severity=5
        )

    def _resolve(self, tier, outcome, strength=None):
        return resolve_fury(
            tier=tier,
            strength=strength or self.strength,
            check_result=_FakeCheck(outcome),
        )

    def test_cap_gate_clamps_deep_tier(self):
        """cap=2, t3.depth=3 > 2 → clamped to the deepest tier within the cap, t1."""
        res = self._resolve(self.t3, self.success)
        self.assertEqual(res.realized_tier, self.t1)
        self.assertEqual(res.control_surrendered, 10)

    def test_full_share_scaled_by_cap(self):
        """10 x 1.5 x 1.2 x 100% = 18."""
        self.assertEqual(self._resolve(self.t1, self.success).intensity_gained, 18)

    def test_better_outcome_buys_more(self):
        """Partial buys 50%: floor(18 x 0.5) = 9."""
        self.assertEqual(self._resolve(self.t1, self.partial).intensity_gained, 9)

    def test_outcome_with_no_share_row_buys_nothing_but_still_surrenders(self):
        res = self._resolve(self.t1, self.unshared)
        self.assertEqual(res.intensity_gained, 0)
        self.assertEqual(res.control_surrendered, 10)

    def test_no_check_buys_nothing(self):
        res = resolve_fury(tier=self.t1, strength=self.strength, check_result=None)
        self.assertEqual(res.intensity_gained, 0)

    def test_berserk_tier_is_chosen_not_rolled(self):
        """A Berserk tier carries its severity even on the best outcome."""
        deep = KindledStrengthTierFactory(
            rank=2, name="Blazing", give_in_max_depth=3, give_in_bonus_percent=20
        )
        res = self._resolve(self.t3, self.success, strength=deep)
        self.assertEqual(res.berserk_severity, 5)

    def test_non_berserk_tier_never_berserks_on_a_bad_roll(self):
        self.assertEqual(self._resolve(self.t1, self.unshared).berserk_severity, 0)


class GivingInToAKindledResonanceTests(TestCase):
    """Giving in reads the kindled strength of the named resonance, and refuses the rest."""

    @classmethod
    def setUpTestData(cls):
        ensure_level_ladder()
        FuryConfigFactory()
        cls.faint = KindledStrengthTierFactory(
            rank=1,
            name="Faint",
            give_in_max_depth=1,
            give_in_bonus_percent=0,
            give_in_ease_tenths=4,
        )
        cls.blazing = KindledStrengthTierFactory(
            rank=3,
            name="Blazing",
            give_in_max_depth=3,
            give_in_bonus_percent=40,
            give_in_ease_tenths=12,
        )
        cls.hold = FuryTierFactory(name="Let it in", depth=1, control_surrendered=2)
        cls.lose = FuryTierFactory(
            name="Lose yourself", depth=3, control_surrendered=9, berserk_severity=5
        )

    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.resonance = ResonanceFactory(name="Wrath")

    def test_an_unkindled_resonance_is_refused_in_words(self):
        self.assertIsNone(give_in_strength(self.sheet, self.resonance))
        self.assertEqual(
            give_in_refusal(self.sheet, self.resonance, self.hold),
            "Your Wrath is not kindled right now, so you cannot give in to it.",
        )

    def test_a_resonance_she_does_not_hold_is_refused(self):
        self.assertIsNotNone(give_in_refusal(self.sheet, ResonanceFactory(), self.hold))

    def test_a_kindled_resonance_gives_in_at_the_tier_row_numbers(self):
        kindle_resonance(self.sheet, self.resonance, self.blazing)
        strength = give_in_strength(self.sheet, self.resonance)
        self.assertEqual(strength, self.blazing)
        self.assertEqual(provocation_cap(strength), 3)
        # 12 tenths of a level's width, read at level 2 (width 8): 12 x 8 / 10 = 9.6 -> 10 points.
        self.assertEqual(provocation_ease(strength, at_level=2), 10)
        self.assertIsNone(give_in_refusal(self.sheet, self.resonance, self.lose))

    def test_berserk_is_offered_only_where_the_strength_reaches_it(self):
        kindle_resonance(self.sheet, self.resonance, self.faint)
        self.assertEqual(provocation_cap(give_in_strength(self.sheet, self.resonance)), 1)
        self.assertIsNone(give_in_refusal(self.sheet, self.resonance, self.hold))
        self.assertEqual(
            give_in_refusal(self.sheet, self.resonance, self.lose),
            "Your Wrath is not kindled enough to give in as far as Lose yourself.",
        )

    def test_no_strength_gives_nothing(self):
        self.assertEqual(provocation_cap(None), 0)
        self.assertEqual(provocation_ease(None, at_level=2), 0)


class _FakeCheck:
    def __init__(self, outcome):
        self.outcome = outcome
        self.success_level = outcome.success_level


class FullTradePreviewTests(TestCase):
    """The picker's "up to" figure uses the highest authored share, not 100% (#4738)."""

    @classmethod
    def setUpTestData(cls):
        FuryConfigFactory()
        config = get_strain_config()
        config.intensity_per_control_surrendered = Decimal("1.50")
        config.save()
        cls.tier = FuryTierFactory(name="Seething", depth=1, control_surrendered=10)

    def test_no_share_rows_preview_nothing(self):
        from world.magic.services.fury import full_trade_intensities

        self.assertEqual(full_trade_intensities([self.tier]), {self.tier.pk: 0})

    def test_preview_uses_the_highest_authored_share(self):
        from world.magic.services.fury import full_trade_intensities

        FuryDegreeShareFactory(
            outcome_tier=CheckOutcomeFactory(name="Partial", success_level=0),
            intensity_percent=40,
        )
        FuryDegreeShareFactory(
            outcome_tier=CheckOutcomeFactory(name="Success", success_level=1),
            intensity_percent=80,
        )
        # 10 x 1.5 = 15 with no bonus; x 80% = 12. A 20% bonus: 18 x 80% = 14.4 -> 14.
        self.assertEqual(full_trade_intensities([self.tier]), {self.tier.pk: 12})
        self.assertEqual(full_trade_intensities([self.tier], 20), {self.tier.pk: 14})
