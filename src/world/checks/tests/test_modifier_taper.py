"""The light taper on piles of check modifiers (#4594, #4551 decision 1).

Each further modifier of a tapered kind counts 7/8 of the one before it, never below
2/3, bonuses and penalties apart; the character's own standing and a vow's step are
never tapered; no rules means a plain sum.
"""

from decimal import Decimal

from django.test import SimpleTestCase

from world.checks.constants import ModifierSourceKind
from world.checks.types import ModifierBreakdown, ModifierContribution, TaperRule

LIGHT = TaperRule(ratio=Decimal("0.875"), floor=Decimal("0.6667"))
CONDITION = ModifierSourceKind.CONDITION


def _buff(value: int, *, kind: str = CONDITION, vow_part: int = 0) -> ModifierContribution:
    return ModifierContribution(
        source_kind=kind, source_label=f"{kind} {value}", value=value, vow_part=vow_part
    )


class TaperRuleTests(SimpleTestCase):
    def test_weights_fall_by_seven_eighths_to_the_floor(self) -> None:
        weights = [LIGHT.weight(position) for position in range(6)]

        self.assertEqual(weights[0], Decimal(1))
        self.assertEqual(weights[1], Decimal("0.875"))
        self.assertEqual(weights[2], Decimal("0.765625"))
        self.assertEqual(weights[3], Decimal("0.669921875"))  # still above the floor
        self.assertEqual(weights[4], Decimal("0.6667"))  # 0.586, held at the floor
        self.assertEqual(weights[5], Decimal("0.6667"))


class ModifierBreakdownTaperTests(SimpleTestCase):
    def test_no_rules_is_a_plain_sum(self) -> None:
        breakdown = ModifierBreakdown(contributions=[_buff(10) for _ in range(10)])

        self.assertEqual(breakdown.total, 100)

    def test_one_buff_is_unchanged(self) -> None:
        breakdown = ModifierBreakdown(contributions=[_buff(10)], tapers={CONDITION: LIGHT})

        self.assertEqual(breakdown.total, 10)

    def test_ten_equal_buffs_taper(self) -> None:
        breakdown = ModifierBreakdown(
            contributions=[_buff(10) for _ in range(10)], tapers={CONDITION: LIGHT}
        )

        # 10 x (1 + 0.875 + 0.765625 + 0.669921875 + 6 x 0.6667) = 73.1
        counted = [c.counted for c in breakdown.counted()]
        self.assertEqual(counted[0], Decimal(10))
        self.assertEqual(counted[1], Decimal("8.750"))
        self.assertEqual(breakdown.total, 73)
        self.assertLess(breakdown.total, 100)
        # Every added buff still adds at least 2/3 of its value.
        self.assertTrue(all(c >= Decimal("6.667") for c in counted))

    def test_the_largest_counts_first(self) -> None:
        breakdown = ModifierBreakdown(
            contributions=[_buff(4), _buff(20)], tapers={CONDITION: LIGHT}
        )

        counted = {c.contribution.value: c.counted for c in breakdown.counted()}
        self.assertEqual(counted[20], Decimal(20))
        self.assertEqual(counted[4], Decimal("3.500"))
        self.assertEqual(breakdown.total, 24)

    def test_bonuses_and_penalties_taper_apart(self) -> None:
        breakdown = ModifierBreakdown(
            contributions=[_buff(10), _buff(-10), _buff(10), _buff(-10)],
            tapers={CONDITION: LIGHT},
        )

        # Each pile is 10 + 8.75; they cancel exactly.
        self.assertEqual(breakdown.total, 0)

    def test_kinds_taper_apart(self) -> None:
        breakdown = ModifierBreakdown(
            contributions=[_buff(10), _buff(10, kind=ModifierSourceKind.EQUIPMENT)],
            tapers={CONDITION: LIGHT, ModifierSourceKind.EQUIPMENT: LIGHT},
        )

        self.assertEqual(breakdown.total, 20)

    def test_own_standing_is_never_tapered(self) -> None:
        breakdown = ModifierBreakdown(
            contributions=[
                _buff(10, kind=ModifierSourceKind.EFFORT),
                _buff(10, kind=ModifierSourceKind.EFFORT),
                _buff(5, kind=ModifierSourceKind.ROLLMOD),
            ],
            tapers={CONDITION: LIGHT},
        )

        self.assertEqual(breakdown.total, 25)

    def test_a_vow_part_rides_outside_the_taper(self) -> None:
        breakdown = ModifierBreakdown(
            contributions=[_buff(10), _buff(16, vow_part=6)],
            tapers={CONDITION: LIGHT},
        )

        # Both taperable parts are 10: the first counts 10, the second 8.75, plus its
        # untouched vow part of 6.
        self.assertEqual(breakdown.total, 25)

    def test_extra_modifiers_total_leaves_capability_out_after_the_taper(self) -> None:
        breakdown = ModifierBreakdown(
            contributions=[_buff(10), _buff(10), _buff(7, kind=ModifierSourceKind.CAPABILITY)],
            tapers={CONDITION: LIGHT},
        )

        self.assertEqual(breakdown.total, 26)
        self.assertEqual(breakdown.extra_modifiers_total, 19)

    def test_counted_values_are_whole_and_sum_to_the_total(self) -> None:
        breakdown = ModifierBreakdown(
            contributions=[
                *(_buff(10) for _ in range(10)),
                _buff(-7),
                _buff(-7),
                _buff(3, kind=ModifierSourceKind.EFFORT),
            ],
            tapers={CONDITION: LIGHT},
        )

        values = breakdown.counted_values()

        self.assertEqual(sum(values), breakdown.total)
        self.assertEqual(values[0], 10)  # the first buff counts whole
        self.assertEqual(values[-1], 3)  # own standing untouched
        self.assertTrue(all(isinstance(v, int) for v in values))
