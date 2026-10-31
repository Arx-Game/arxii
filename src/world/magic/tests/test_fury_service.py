"""Tests for the fury resolution service (provocation cap, clamp, the bought share)."""

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.services.encounter.config import get_strain_config
from world.magic.factories import FuryConfigFactory, FuryDegreeShareFactory, FuryTierFactory
from world.magic.services.fury import (
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


def _mutual_teaching_bond_at_tier(*, source_sheet, target_sheet, tier: int):
    """Establish a mutual Mentor/Student bond at the given tier on both sides.

    Fury itself needs only the SOURCE side's tier (``fury._bond_tier``, any label), so this
    builds more than the cap strictly reads: it is kept mutual-TEACHING so these fixtures
    keep proving the cap is unchanged for the shape training's ``get_relationship_tier``
    also recognises. ``ProvocationCapReadsOwnSideTests`` covers the one-sided case.
    """
    mentor = RelationshipTypeFactory(family=TypeFamily.TEACHING)
    student = RelationshipTypeFactory(family=TypeFamily.TEACHING, counterpart=mentor)
    mentor.counterpart = student
    mentor.save(update_fields=["counterpart"])
    forward = CharacterRelationshipFactory(source=source_sheet, target=target_sheet, tier=tier)
    backward = CharacterRelationshipFactory(source=target_sheet, target=source_sheet, tier=tier)
    forward_tenure = grant_test_tenure(source_sheet)
    backward_tenure = grant_test_tenure(target_sheet)
    declare_label(side=forward, type=mentor, awareness=LabelAwareness.PUBLIC, tenure=forward_tenure)
    declare_label(
        side=backward, type=student, awareness=LabelAwareness.PUBLIC, tenure=backward_tenure
    )
    return forward


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


class ResolveFuryNullAnchorTests(TestCase):
    """Null anchor (real character, anchor=None) → fury unavailable."""

    @classmethod
    def setUpTestData(cls):
        FuryConfigFactory()
        cls.t1 = FuryTierFactory(name="Smouldering", depth=1, control_surrendered=2)
        cls.character = CharacterSheetFactory()

    def test_null_anchor_returns_unavailable(self):
        """anchor=None → cap=0 → clamp returns None → nothing surrendered or bought."""
        res = resolve_fury(
            character=self.character.character,
            tier=self.t1,
            anchor=None,
            check_result=_FakeCheck(CheckOutcomeFactory(name="Success", success_level=1)),
        )
        self.assertIsNone(res.realized_tier)
        self.assertEqual(res.control_surrendered, 0)
        self.assertEqual(res.intensity_gained, 0)
        self.assertEqual(res.berserk_severity, 0)


class ResolveFuryRealBondTests(TestCase):
    """resolve_fury with a real bonded pair: cap → clamp → the share the outcome buys.

    Bond tier 2 → cap 2 → x1.2 scale. 1.50 intensity per control surrendered.
    Smouldering surrenders 10: full trade 10 x 1.5 x 1.2 = 18.
    """

    @classmethod
    def setUpTestData(cls):
        FuryConfigFactory(
            provocation_cap_per_tier=1,  # 1 relationship tier = 1 fury tier cap
            bonus_scale_per_cap_point=10,  # 10% more per cap point
            cap_ease_per_point=2,
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
        # Build a real bonded pair: mutual Mentor/Student bond at tier 2.
        cls.source_sheet = CharacterSheetFactory()
        cls.anchor_sheet = CharacterSheetFactory()
        _mutual_teaching_bond_at_tier(
            source_sheet=cls.source_sheet, target_sheet=cls.anchor_sheet, tier=2
        )

    def _resolve(self, tier, outcome):
        return resolve_fury(
            character=self.source_sheet.character,
            tier=tier,
            anchor=self.anchor_sheet,
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
            anchor=self.anchor_sheet,
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
    """provocation_ease exercises cap * cap_ease_per_point — verifies cap_ease_per_point exists."""

    @classmethod
    def setUpTestData(cls):
        FuryConfigFactory(
            provocation_cap_per_tier=1,
            cap_ease_per_point=3,
        )
        cls.source_sheet = CharacterSheetFactory()
        cls.anchor_sheet = CharacterSheetFactory()
        _mutual_teaching_bond_at_tier(
            source_sheet=cls.source_sheet, target_sheet=cls.anchor_sheet, tier=2
        )

    def test_provocation_ease_uses_cap_ease_per_point(self):
        """cap=2 (relationship tier 2, per_tier=1), cap_ease_per_point=3 → ease=6."""
        ease = provocation_ease(
            self.source_sheet.character,
            self.anchor_sheet,
        )
        self.assertEqual(ease, 6)  # cap=2, 2*3=6

    def test_provocation_ease_zero_for_null_anchor(self):
        ease = provocation_ease(self.source_sheet.character, None)
        self.assertEqual(ease, 0)


class ProvocationCapReadsOwnSideTests(TestCase):
    """The cap reads the character's OWN side toward the anchor, any label (#3957 fix round 1).

    Fury's provocation cap has always been one-sided and label-agnostic: a character can be
    provoked over someone who never declared anything back. It deliberately does NOT go
    through ``relationships.helpers.get_relationship_tier``, which is training's narrower
    mentor helper (the lower tier of a MUTUAL Teaching-family tie).
    """

    @classmethod
    def setUpTestData(cls):
        FuryConfigFactory(provocation_cap_per_tier=1, cap_ease_per_point=2)
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

    def test_one_sided_non_teaching_tie_still_caps_at_its_tier(self):
        """Tier 2 with per_tier=1 → cap 2, the same value a mutual Mentor/Student tie gives."""
        self.assertEqual(
            provocation_cap(self.source_sheet.character, self.anchor_sheet),
            2,
        )

    def test_no_tie_gives_zero(self):
        self.assertEqual(
            provocation_cap(self.source_sheet.character, self.unrelated_sheet),
            0,
        )


class _FakeCheck:
    def __init__(self, outcome):
        self.outcome = outcome
        self.success_level = outcome.success_level


class FullTradePreviewTests(TestCase):
    """The picker's "up to" figure uses the highest authored share, not 100% (#4738)."""

    @classmethod
    def setUpTestData(cls):
        FuryConfigFactory(bonus_scale_per_cap_point=10)
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
        # 10 x 1.5 = 15 at no cap; x 80% = 12. Cap 2 scales by 1.2: 18 x 80% = 14.4 -> 14.
        self.assertEqual(full_trade_intensities([self.tier]), {self.tier.pk: 12})
        self.assertEqual(full_trade_intensities([self.tier], 2), {self.tier.pk: 14})
