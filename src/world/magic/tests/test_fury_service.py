"""Tests for the fury resolution service (provocation cap, clamp, control-retention outcome)."""

from django.test import TestCase

from world.magic.factories import FuryConfigFactory, FuryTierFactory
from world.magic.services.fury import clamp_tier, resolve_fury


class FuryServiceTests(TestCase):
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
        self.assertIsNone(clamp_tier(self.t1, cap=0))

    def test_resolve_lucid_when_check_meets_floor(self):
        res = resolve_fury(
            character=None,
            tier=self.t1,
            anchor=None,
            check_result=_FakeCheck(success_level=3),
        )
        self.assertEqual(res.berserk_severity, 0)
        self.assertEqual(res.control_penalty, 2)

    def test_resolve_berserk_below_floor(self):
        res = resolve_fury(
            character=None,
            tier=self.t3,
            anchor=None,
            check_result=_FakeCheck(success_level=1),
        )
        self.assertEqual(res.berserk_severity, 5)


class _FakeCheck:
    def __init__(self, success_level):
        self.success_level = success_level
