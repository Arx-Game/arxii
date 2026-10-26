"""Tests for ``train_skill`` and ``points_to_next_boundary`` (#4457)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.classes.models import PathStage
from world.progression.models import MaturationStatCap
from world.progression.models.rewards import DevelopmentTransaction
from world.progression.types import DevelopmentSource
from world.skills.factories import CharacterSkillValueFactory, SkillFactory
from world.skills.models import CharacterSkillValue
from world.skills.services import points_to_next_boundary, train_skill
from world.traits.models import CharacterTraitValue


class PointsToNextBoundaryTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.sheet = CharacterSheetFactory()
        cls.skill = SkillFactory()

    def _row(self, **kwargs: int) -> CharacterSkillValue:
        return CharacterSkillValueFactory.build(character=self.sheet, skill=self.skill, **kwargs)

    def test_points_to_next_boundary_from_ten(self) -> None:
        row = self._row(value=10)
        self.assertEqual(points_to_next_boundary(row), 4500)

    def test_points_to_next_boundary_counts_rust_and_banked(self) -> None:
        row = self._row(value=15, rust_points=50, development_points=120)
        self.assertEqual(points_to_next_boundary(row), 50 + (600 - 120) + 700 + 800 + 900)

    def test_points_to_next_boundary_at_boundary_is_rust(self) -> None:
        self.assertEqual(points_to_next_boundary(self._row(value=19, rust_points=30)), 30)
        self.assertEqual(points_to_next_boundary(self._row(value=19, rust_points=0)), 0)

    def test_points_to_next_boundary_above_fifty_is_none(self) -> None:
        self.assertIsNone(points_to_next_boundary(self._row(value=52)))

    def test_points_to_next_boundary_in_a_later_decade(self) -> None:
        """From 20 the next boundary is 29: 1100 + 1200 + ... + 1900."""
        row = self._row(value=20)
        self.assertEqual(points_to_next_boundary(row), sum(range(1100, 2000, 100)))


class PointsToNextBoundaryAtABandCapTests(TestCase):
    """The band's skill cap (#4585) is a stop like an XP boundary. The sheet has no
    class level, so level 1 and the first band's row bind it."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.sheet = CharacterSheetFactory()
        cls.skill = SkillFactory()
        MaturationStatCap.objects.create(path_stage=PathStage.PROSPECT, stat_cap=5, skill_cap=6)

    def _row(self, **kwargs: int) -> CharacterSkillValue:
        return CharacterSkillValueFactory.build(character=self.sheet, skill=self.skill, **kwargs)

    def test_above_fifty_the_count_ends_at_the_cap(self) -> None:
        """Cap 6 is stored 60: from 57, 4800 + 4900 + 5000 less 100 banked."""
        row = self._row(value=57, development_points=100)
        self.assertEqual(points_to_next_boundary(row), 4800 + 4900 + 5000 - 100)

    def test_at_the_cap_only_rust_is_taken(self) -> None:
        self.assertEqual(points_to_next_boundary(self._row(value=60, rust_points=12)), 12)
        self.assertEqual(points_to_next_boundary(self._row(value=64, rust_points=0)), 0)

    def test_below_the_cap_the_boundary_still_comes_first(self) -> None:
        self.assertEqual(points_to_next_boundary(self._row(value=10)), 4500)


class TrainSkillTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.sheet = CharacterSheetFactory()
        cls.skill = SkillFactory()

    def test_train_skill_creates_row_at_ten(self) -> None:
        result = train_skill(self.sheet, self.skill, 300, description="x")

        self.assertEqual(result.old_value, 10)
        self.assertEqual(result.new_value, 12)
        self.assertEqual(result.points_applied, 300)
        self.assertIsNone(result.plateau_message)
        transaction = DevelopmentTransaction.objects.get(character_sheet=self.sheet)
        self.assertEqual(transaction.amount, 300)
        self.assertEqual(transaction.source, DevelopmentSource.TRAINING)
        self.assertEqual(transaction.trait, self.skill.trait)
        self.assertEqual(
            CharacterTraitValue.objects.get(character=self.sheet, trait=self.skill.trait).value,
            12,
        )

    def test_train_skill_stop_at_boundary_keeps_excess(self) -> None:
        CharacterSkillValueFactory(character=self.sheet, skill=self.skill, value=18)

        result = train_skill(self.sheet, self.skill, 1500, description="x", stop_at_boundary=True)

        self.assertEqual(result.new_value, 19)
        self.assertEqual(result.points_applied, 900)
        self.assertIsNone(result.plateau_message)
        self.assertEqual(DevelopmentTransaction.objects.get().amount, 900)

    def test_train_skill_without_stop_dissipates_at_boundary(self) -> None:
        CharacterSkillValueFactory(character=self.sheet, skill=self.skill, value=18)

        result = train_skill(self.sheet, self.skill, 1500, description="Weekly")

        self.assertEqual(result.new_value, 19)
        self.assertEqual(result.points_applied, 1500)
        self.assertIsNotNone(result.plateau_message)
        transaction = DevelopmentTransaction.objects.get()
        self.assertEqual(transaction.amount, 1500)
        self.assertTrue(transaction.description.endswith(result.plateau_message))
