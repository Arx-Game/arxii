"""Tests for the fury resolution service (strength cap, clamp, the bought share)."""

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.services.encounter.config import get_strain_config
from world.magic.factories import (
    FuryConfigFactory,
    FuryDegreeShareFactory,
    FuryTierFactory,
    KindledStrengthTierFactory,
    ResonanceFactory,
)
from world.magic.services.fury import (
    _bond_tier,
    clamp_tier,
    provocation_cap,
    provocation_ease,
    resolve_fury,
)
from world.relationships.constants import LabelAwareness, TypeFamily
from world.relationships.factories import CharacterRelationshipFactory, RelationshipTypeFactory
from world.relationships.services import declare_label
from world.roster.factories import grant_test_tenure
from world.traits.factories import CheckOutcomeFactory


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
            character=self.character.character,
            tier=self.t1,
            resonance=None,
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
        KindledStrengthTierFactory(
            rank=3, give_in_max_depth=2, give_in_bonus_percent=20, give_in_ease=4
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
        cls.source_sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()

    def _resolve(self, tier, outcome):
        return resolve_fury(
            character=self.source_sheet.character,
            tier=tier,
            resonance=self.resonance,
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
        res = resolve_fury(
            character=self.source_sheet.character,
            tier=self.t1,
            resonance=self.resonance,
            check_result=None,
        )
        self.assertEqual(res.intensity_gained, 0)

    def test_berserk_tier_is_chosen_not_rolled(self):
        """A Berserk tier carries its severity even on the best outcome."""
        with patch("world.magic.services.fury.provocation_cap", return_value=3):
            res = self._resolve(self.t3, self.success)
        self.assertEqual(res.berserk_severity, 5)

    def test_non_berserk_tier_never_berserks_on_a_bad_roll(self):
        self.assertEqual(self._resolve(self.t1, self.unshared).berserk_severity, 0)


class ProvocationEaseTests(TestCase):
    """provocation_ease reads the strength row's give_in_ease."""

    @classmethod
    def setUpTestData(cls):
        FuryConfigFactory()
        KindledStrengthTierFactory(rank=3, give_in_max_depth=2, give_in_ease=6)
        cls.source_sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()

    def test_provocation_ease_reads_the_strength_row(self):
        self.assertEqual(provocation_ease(self.source_sheet.character, self.resonance), 6)
        self.assertEqual(provocation_cap(self.source_sheet.character, self.resonance), 2)

    def test_provocation_ease_zero_for_no_resonance(self):
        self.assertEqual(provocation_ease(self.source_sheet.character, None), 0)

    def test_no_strength_row_gives_nothing(self):
        from world.magic.models import KindledStrengthTier

        KindledStrengthTier.objects.all().delete()
        self.assertEqual(provocation_cap(self.source_sheet.character, self.resonance), 0)
        self.assertEqual(provocation_ease(self.source_sheet.character, self.resonance), 0)


class BondTierReadsOwnSideTests(TestCase):
    """The bond tier reads the character's OWN side toward the anchor, any label (#3957).

    A character can be provoked over someone who never declared anything back. It deliberately
    does NOT go through ``relationships.helpers.get_relationship_tier``, which is training's
    narrower mentor helper (the lower tier of a MUTUAL Teaching-family tie). Kindling reads
    it for the strength of a thread anchor (#5124).
    """

    @classmethod
    def setUpTestData(cls):
        cls.source_sheet = CharacterSheetFactory()
        cls.anchor_sheet = CharacterSheetFactory()
        cls.unrelated_sheet = CharacterSheetFactory()
        # A one-sided Heart-family (Lover) tie at tier 2: no Teaching label, no reverse row.
        lover = RelationshipTypeFactory(family=TypeFamily.HEART)
        side = CharacterRelationshipFactory(
            source=cls.source_sheet, target=cls.anchor_sheet, tier=2
        )
        declare_label(
            side=side,
            type=lover,
            awareness=LabelAwareness.PUBLIC,
            tenure=grant_test_tenure(cls.source_sheet),
        )

    def test_one_sided_non_teaching_tie_reads_its_tier(self):
        self.assertEqual(_bond_tier(self.source_sheet.character, self.anchor_sheet), 2)

    def test_no_tie_gives_zero(self):
        self.assertEqual(_bond_tier(self.source_sheet.character, self.unrelated_sheet), 0)


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
