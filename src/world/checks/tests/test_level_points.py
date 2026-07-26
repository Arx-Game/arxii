"""Tests for the guaranteed level term in the shared check breakdown (#2707).

Level was previously only reachable through the aspect bonus, which is zero unless
a CheckType has an authored CheckTypeAspect matching the character's Path — so on
most checks level did nothing at all. ``LEVEL_POINTS_PER_LEVEL`` folds level into
``_compute_check_breakdown`` directly, so every consumer (the rolled path, the
forced-outcome test path, ``compute_check_rating``, and ``preview_check_difficulty``)
inherits it.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import LEVEL_POINTS_PER_LEVEL
from world.checks.factories import CheckCategoryFactory, CheckTypeFactory
from world.checks.services import compute_check_rating, perform_check, preview_check_difficulty
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.traits.factories import CheckSystemSetupFactory
from world.traits.models import CheckRank, PointConversionRange, ResultChart, Trait, TraitType


class LevelPointsTests(TestCase):
    """Level contributes LEVEL_POINTS_PER_LEVEL points per level to every check."""

    @classmethod
    def setUpTestData(cls):
        Trait.flush_instance_cache()
        CheckSystemSetupFactory.create()
        # Create PointConversionRange for stats (CheckSystemSetupFactory only creates
        # outcomes and charts, not conversion ranges or ranks).
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.STAT,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )
        # Create CheckRank entries for the point-to-rank pipeline
        for rank_val, min_pts, name in [
            (0, 0, "LevelTestNone"),
            (1, 10, "LevelTestNovice"),
            (2, 25, "LevelTestCompetent"),
            (3, 50, "LevelTestExpert"),
        ]:
            CheckRank.objects.get_or_create(
                rank=rank_val,
                defaults={"min_points": min_pts, "name": name},
            )

        character_class = CharacterClassFactory()

        sheet_one = CharacterSheetFactory()
        CharacterClassLevelFactory(
            character=sheet_one,
            character_class=character_class,
            level=1,
            is_primary=True,
        )
        cls.level_one_character = sheet_one.character

        sheet_five = CharacterSheetFactory()
        CharacterClassLevelFactory(
            character=sheet_five,
            character_class=character_class,
            level=5,
            is_primary=True,
        )
        cls.level_five_character = sheet_five.character

        cls.category = CheckCategoryFactory(name="check_test_level_points")
        cls.check_type = CheckTypeFactory(name="check_test_level_points", category=cls.category)

    def setUp(self):
        Trait.flush_instance_cache()
        ResultChart.clear_cache()

    def test_level_contributes_points(self):
        low = compute_check_rating(self.level_one_character, self.check_type)
        high = compute_check_rating(self.level_five_character, self.check_type)
        self.assertEqual(high - low, LEVEL_POINTS_PER_LEVEL * 4)

    def test_level_points_reported_on_result(self):
        result = perform_check(self.level_five_character, self.check_type)
        self.assertEqual(result.level_points, LEVEL_POINTS_PER_LEVEL * 5)
        self.assertIn(result.level_points, range(result.total_points + 1))

    def test_four_level_gap_spans_two_rungs_on_level_alone(self):
        """Decision 4: brutal magnitude. Level alone, no traits."""
        self.assertEqual(CheckRank.get_rank_for_points(LEVEL_POINTS_PER_LEVEL * 1).rank, 0)
        self.assertEqual(CheckRank.get_rank_for_points(LEVEL_POINTS_PER_LEVEL * 5).rank, 2)

    def test_preview_matches_the_real_breakdown(self):
        """preview_check_difficulty must not re-derive the formula (it used to)."""
        result = perform_check(self.level_five_character, self.check_type, target_difficulty=25)
        preview = preview_check_difficulty(
            self.level_five_character, self.check_type, target_difficulty=25
        )
        self.assertEqual(preview, result.rank_difference)
