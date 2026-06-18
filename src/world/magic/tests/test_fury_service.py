"""Tests for the fury resolution service (provocation cap, clamp, control-retention outcome)."""

from unittest.mock import patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import FuryConfigFactory, FuryTierFactory
from world.magic.services.fury import (
    clamp_tier,
    provocation_ease,
    resolve_fury,
)
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipTierFactory,
    RelationshipTrackFactory,
    RelationshipTrackProgressFactory,
)


class ClampTierTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        FuryConfigFactory()
        cls.t1 = FuryTierFactory(
            name="Smouldering",
            depth=1,
            control_penalty=2,
            intensity_bonus=2,
            lucid_grade_floor=1,
            berserk_severity=0,
        )
        cls.t3 = FuryTierFactory(
            name="Berserk",
            depth=3,
            control_penalty=8,
            intensity_bonus=10,
            lucid_grade_floor=3,
            berserk_severity=5,
        )

    def test_clamp_drops_tier_above_cap(self):
        self.assertEqual(clamp_tier(self.t3, cap=1), self.t1)

    def test_clamp_returns_none_when_cap_zero(self):
        self.assertIsNone(clamp_tier(self.t1, cap=0))


class ResolveFuryNullAnchorTests(TestCase):
    """Null anchor (real character, anchor=None) → fury unavailable."""

    @classmethod
    def setUpTestData(cls):
        FuryConfigFactory()
        cls.t1 = FuryTierFactory(
            name="Smouldering",
            depth=1,
            control_penalty=2,
            intensity_bonus=2,
            lucid_grade_floor=1,
            berserk_severity=0,
        )
        cls.character = CharacterSheetFactory()

    def test_null_anchor_returns_unavailable(self):
        """anchor=None → cap=0 → clamp returns None → FuryResolution(None, 0, 0, 0)."""
        res = resolve_fury(
            character=self.character.character,
            tier=self.t1,
            anchor=None,
            check_result=_FakeCheck(success_level=5),
        )
        self.assertIsNone(res.realized_tier)
        self.assertEqual(res.control_penalty, 0)
        self.assertEqual(res.intensity_bonus, 0)
        self.assertEqual(res.berserk_severity, 0)


class ResolveFuryRealBondTests(TestCase):
    """resolve_fury with a real bonded pair exercises provocation_cap → clamp → bonus arithmetic."""

    @classmethod
    def setUpTestData(cls):
        FuryConfigFactory(
            provocation_cap_per_tier=1,  # 1 relationship tier = 1 fury tier cap
            bonus_scale_per_cap_point=10,  # 10% bonus per cap point
            cap_ease_per_point=2,
        )
        cls.t1 = FuryTierFactory(
            name="Smouldering",
            depth=1,
            control_penalty=2,
            intensity_bonus=10,
            lucid_grade_floor=1,
            berserk_severity=0,
        )
        cls.t3 = FuryTierFactory(
            name="Infernal",
            depth=3,
            control_penalty=8,
            intensity_bonus=30,
            lucid_grade_floor=3,
            berserk_severity=5,
        )
        # Build a real bonded pair: source sheet bonds to target sheet at tier 2.
        cls.source_sheet = CharacterSheetFactory()
        cls.anchor_sheet = CharacterSheetFactory()
        track = RelationshipTrackFactory()
        # RelationshipTier at tier_number=2 with point_threshold=20.
        tier_row = RelationshipTierFactory(
            track=track,
            tier_number=2,
            point_threshold=20,
        )
        rel = CharacterRelationshipFactory(
            source=cls.source_sheet,
            target=cls.anchor_sheet,
        )
        RelationshipTrackProgressFactory(
            relationship=rel,
            track=track,
            developed_points=tier_row.point_threshold,
            capacity=tier_row.point_threshold,
        )

    def test_cap_gate_clamps_deep_tier(self):
        """With relationship tier 2 → cap=2 (per_tier=1); t3 depth=3 > cap → clamped to t1."""
        res = resolve_fury(
            character=self.source_sheet.character,
            tier=self.t3,
            anchor=self.anchor_sheet,
            check_result=_FakeCheck(success_level=5),
        )
        # cap=2, t3.depth=3 > 2 → clamp to deepest tier with depth <= 2 = t1 (depth=1)
        self.assertEqual(res.realized_tier, self.t1)

    def test_bonus_scaled_by_cap(self):
        """With cap=2 and bonus_scale=10%, intensity_bonus=10 → 10*(100+20)//100 = 12."""
        res = resolve_fury(
            character=self.source_sheet.character,
            tier=self.t1,
            anchor=self.anchor_sheet,
            check_result=_FakeCheck(success_level=5),
        )
        # 10 * (100 + 10*2) // 100 = 10 * 120 // 100 = 12
        self.assertEqual(res.intensity_bonus, 12)

    def test_lucid_when_check_meets_floor(self):
        """success_level >= lucid_grade_floor → berserk_severity=0."""
        res = resolve_fury(
            character=self.source_sheet.character,
            tier=self.t1,
            anchor=self.anchor_sheet,
            check_result=_FakeCheck(success_level=3),
        )
        self.assertEqual(res.berserk_severity, 0)

    def test_berserk_below_floor(self):
        """success_level < lucid_grade_floor → berserk_severity > 0.

        We need t3 within the cap, so patch provocation_cap to return 3.
        """
        with patch("world.magic.services.fury.provocation_cap", return_value=3):
            res = resolve_fury(
                character=self.source_sheet.character,
                tier=self.t3,
                anchor=self.anchor_sheet,
                check_result=_FakeCheck(success_level=1),
            )
        # t3.lucid_grade_floor=3, success_level=1 < 3 → berserk
        self.assertEqual(res.berserk_severity, 5)

    def test_control_penalty_on_realized_tier(self):
        """control_penalty comes from the realized (possibly clamped) tier."""
        res = resolve_fury(
            character=self.source_sheet.character,
            tier=self.t1,
            anchor=self.anchor_sheet,
            check_result=_FakeCheck(success_level=5),
        )
        self.assertEqual(res.control_penalty, self.t1.control_penalty)


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
        track = RelationshipTrackFactory()
        tier_row = RelationshipTierFactory(track=track, tier_number=2, point_threshold=20)
        rel = CharacterRelationshipFactory(
            source=cls.source_sheet,
            target=cls.anchor_sheet,
        )
        RelationshipTrackProgressFactory(
            relationship=rel,
            track=track,
            developed_points=tier_row.point_threshold,
            capacity=tier_row.point_threshold,
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


class _FakeCheck:
    def __init__(self, success_level):
        self.success_level = success_level
