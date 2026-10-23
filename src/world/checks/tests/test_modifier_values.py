"""The value table, level baselines and taper rows, read through the pipeline (#4594)."""

from decimal import Decimal

from django.test import SimpleTestCase, TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import ModifierLane, ModifierSize, ModifierSourceKind
from world.checks.factories import CheckTypeFactory
from world.checks.modifier_models import ModifierLevelBaseline, ModifierTaper, ModifierValue
from world.checks.modifier_values import (
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
    TABLE = ValueTable(rows_by_size={ModifierSize.LARGE: [(1, 3), (6, 10), (11, 16)]})

    def test_sparse_rows_read_as_steps(self) -> None:
        self.assertEqual(self.TABLE.value(1, ModifierSize.LARGE), 3)
        self.assertEqual(self.TABLE.value(5, ModifierSize.LARGE), 3)
        self.assertEqual(self.TABLE.value(6, ModifierSize.LARGE), 10)
        self.assertEqual(self.TABLE.value(30, ModifierSize.LARGE), 16)

    def test_no_row_for_the_size_or_below_the_first_level(self) -> None:
        self.assertIsNone(self.TABLE.value(6, ModifierSize.MINOR))
        table = ValueTable(rows_by_size={ModifierSize.LARGE: [(3, 7)]})
        self.assertIsNone(table.value(2, ModifierSize.LARGE))


class ModifierRowReadersTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        ModifierValue.objects.create(
            lane=ModifierLane.CHECK, level=6, size=ModifierSize.LARGE, value=10
        )
        ModifierLevelBaseline.objects.create(lane=ModifierLane.CHECK, level=1, baseline=18)
        ModifierLevelBaseline.objects.create(lane=ModifierLane.CHECK, level=6, baseline=58)
        ModifierTaper.objects.create(
            lane=ModifierLane.CHECK,
            source_kind=ModifierSourceKind.CONDITION,
            ratio=Decimal("0.8750"),
            floor=Decimal("0.6667"),
        )
        for rank, min_points, name in ((2, 25, "Competent"), (3, 50, "Expert"), (4, 80, "Master")):
            CheckRank.objects.get_or_create(
                rank=rank, defaults={"min_points": min_points, "name": name}
            )

    def test_the_value_table_loads_in_one_query(self) -> None:
        with self.assertNumQueries(1):
            table = load_value_table()

        self.assertEqual(table.value(7, ModifierSize.LARGE), 10)

    def test_taper_rules_by_kind(self) -> None:
        rules = load_taper_rules()

        self.assertEqual(set(rules), {ModifierSourceKind.CONDITION})
        self.assertEqual(rules[ModifierSourceKind.CONDITION].ratio, Decimal("0.8750"))

    def test_level_baseline_steps(self) -> None:
        self.assertEqual(level_baseline(4), 18)
        self.assertEqual(level_baseline(9), 58)

    def test_rank_band_share_reads_a_value_in_ranks(self) -> None:
        # 58 sits in Expert (50 to 80): a band of 30, so 10 points is a third of a rank.
        self.assertEqual(rank_band_share(10, 58), Decimal("0.33"))


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
