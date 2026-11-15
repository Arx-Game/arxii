"""The value table, level baselines and taper rows, read through the pipeline (#4594)."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import ModifierLane, ModifierSize, ModifierSourceKind
from world.checks.factories import CheckTypeFactory
from world.checks.modifier_models import (
    ModifierLevelBaseline,
    ModifierSizeFraction,
    ModifierTaper,
    ModifierValue,
)
from world.checks.modifier_values import (
    BaselineTable,
    ValueTable,
    level_baseline,
    load_taper_rules,
    load_value_table,
    rank_band_share,
)
from world.checks.services import collect_check_modifiers
from world.conditions.factories import (
    ConditionCheckModifierFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.conditions.services import opponent_condition_opposition
from world.traits.models import CheckRank


class ValueTableLookupTests(SimpleTestCase):
    TABLE = ValueTable(
        overrides={(1, ModifierSize.LARGE): 3, (6, ModifierSize.LARGE): 10},
        fractions={ModifierSize.LARGE: Decimal("0.5")},
        baselines=BaselineTable(levels=(1, 2, 3, 4), baselines=(18, 26, 34, 42)),
    )

    def test_an_override_row_covers_only_its_own_level(self) -> None:
        self.assertEqual(self.TABLE.value(1, ModifierSize.LARGE), 3)
        self.assertEqual(self.TABLE.value(6, ModifierSize.LARGE), 10)
        # Level 2 has no override: half of its width of 8.
        self.assertEqual(self.TABLE.value(2, ModifierSize.LARGE), 4)

    def test_no_fraction_for_the_size_means_no_value(self) -> None:
        self.assertIsNone(self.TABLE.value(2, ModifierSize.MINOR))


class ModifierRowReadersTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        ModifierValue.objects.create(
            lane=ModifierLane.CHECK, level=6, size=ModifierSize.LARGE, value=10
        )
        for level in range(1, 7):
            ModifierLevelBaseline.objects.create(
                lane=ModifierLane.CHECK, level=level, baseline=18 + 8 * (level - 1)
            )
        ModifierTaper.objects.create(
            lane=ModifierLane.CHECK,
            source_kind=ModifierSourceKind.CONDITION,
            ratio=Decimal("0.8750"),
            floor=Decimal("0.6667"),
        )
        for rank in range(2, 7):
            CheckRank.objects.create(rank=rank, name=f"Rank {rank}")

    def test_the_value_table_loads_in_three_queries(self) -> None:
        with self.assertNumQueries(3):
            table = load_value_table()

        self.assertEqual(table.value(6, ModifierSize.LARGE), 10)

    def test_taper_rules_by_kind(self) -> None:
        rules = load_taper_rules()

        self.assertEqual(set(rules), {ModifierSourceKind.CONDITION})
        self.assertEqual(rules[ModifierSourceKind.CONDITION].ratio, Decimal("0.8750"))

    def test_level_baseline_reads_its_row_and_reuses_the_top_one_above_it(self) -> None:
        self.assertEqual(level_baseline(4), 42)
        self.assertEqual(level_baseline(9), 58)

    def test_rank_band_share_reads_a_value_in_level_widths(self) -> None:
        # 58 is rank 6, whose level width is 8: 4 points is half a rank.
        self.assertEqual(rank_band_share(4, 58), Decimal("0.50"))


class PipelineTaperTests(TestCase):
    """collect_check_modifiers applies the taper rows; opposition tapers too."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.check_type = CheckTypeFactory(name="Taper pipeline check")
        cls.sheet = CharacterSheetFactory()
        for index in range(3):
            condition = ConditionTemplateFactory(name=f"Blessing {index}")
            ConditionCheckModifierFactory(
                condition=condition, check_type=cls.check_type, modifier_value=10
            )
            ConditionInstanceFactory(target=cls.sheet.character, condition=condition)

    def test_without_rows_a_pile_is_a_plain_sum(self) -> None:
        breakdown = collect_check_modifiers(self.sheet, self.check_type)

        self.assertEqual(breakdown.total, 30)

    def test_with_a_condition_row_the_pile_tapers(self) -> None:
        ModifierTaper.objects.create(
            lane=ModifierLane.CHECK,
            source_kind=ModifierSourceKind.CONDITION,
            ratio=Decimal("0.8750"),
            floor=Decimal("0.6667"),
        )

        breakdown = collect_check_modifiers(self.sheet, self.check_type)

        # 10 + 8.75 + 7.66 = 26.4
        self.assertEqual(breakdown.total, 26)
        self.assertEqual(breakdown.extra_modifiers_total, 26)

    def test_an_opponents_own_conditions_taper_the_same_way(self) -> None:
        self.assertEqual(opponent_condition_opposition(self.sheet.character, self.check_type), 30)
        ModifierTaper.objects.create(
            lane=ModifierLane.CHECK,
            source_kind=ModifierSourceKind.CONDITION,
            ratio=Decimal("0.8750"),
            floor=Decimal("0.6667"),
        )

        self.assertEqual(opponent_condition_opposition(self.sheet.character, self.check_type), 26)


class SizedLaneOnlyTests(SimpleTestCase):
    """U-keep: staff form validation on rows, no player seam."""

    def test_a_lane_with_no_sizes_refuses_size_fractions_overrides_and_tapers(self) -> None:
        rows = (
            ModifierSizeFraction(lane=ModifierLane.ANIMA_POOL, size=3, fraction=Decimal("0.5")),
            ModifierValue(lane=ModifierLane.MOON_TUNING, level=1, size=3, value=4),
            ModifierTaper(
                lane=ModifierLane.HOLLOW_MAX,
                source_kind=ModifierSourceKind.CONDITION,
                ratio=Decimal("0.5"),
                floor=Decimal("0.5"),
            ),
        )
        for row in rows:
            with self.subTest(row=type(row).__name__), self.assertRaises(ValidationError) as caught:
                row.clean()
            self.assertIn("lane", caught.exception.message_dict)

    def test_a_sized_lane_is_accepted(self) -> None:
        ModifierSizeFraction(lane=ModifierLane.TO_HIT, size=3, fraction=Decimal("0.5")).clean()
