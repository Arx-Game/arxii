"""Tests for the guaranteed level term in the shared check breakdown (#2707).

Level was previously only reachable through the aspect bonus, which is zero unless
a CheckType has an authored CheckTypeAspect matching the character's Path — so on
most checks level did nothing at all. ``level_points`` (the share of the level's baseline,
#5093) folds level into
``_compute_check_breakdown`` directly, so every consumer (the rolled path, the
forced-outcome test path, ``compute_check_rating``, and ``preview_check_difficulty``)
inherits it.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckCategoryFactory, CheckTypeFactory
from world.checks.services import compute_check_rating, perform_check, preview_check_difficulty
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.traits.factories import CheckSystemSetupFactory, ensure_level_ladder
from world.traits.models import CheckRank, PointConversionRange, ResultChart, Trait, TraitType


class LevelPointsTests(TestCase):
    """Level contributes half of its baseline to every check."""

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
        # The standard ladder: baselines 18 + 8 x (level - 1), level share 0.5 (the migrated row).
        ensure_level_ladder()

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
        # Half of level 5's baseline (50) is 25; half of level 1's (18) is 9.
        self.assertEqual(high - low, 25 - 9)

    def test_level_points_reported_on_result(self):
        result = perform_check(self.level_five_character, self.check_type)
        self.assertEqual(result.level_points, 25)
        self.assertIn(result.level_points, range(result.total_points + 1))

    def test_level_alone_lands_in_a_lower_rank_than_its_own(self):
        """Level carries half of the baseline, so level alone sits about half the rank number.

        Level 5's term is 25, which is rank 1 (18 to 25); level 1's term is 9, below rank 1.
        """
        self.assertEqual(CheckRank.get_rank_for_points(9).rank, 0)
        self.assertEqual(CheckRank.get_rank_for_points(25).rank, 1)

    def test_preview_matches_the_real_breakdown(self):
        """preview_check_difficulty must not re-derive the formula (it used to)."""
        result = perform_check(self.level_five_character, self.check_type, target_difficulty=25)
        preview = preview_check_difficulty(
            self.level_five_character, self.check_type, target_difficulty=25
        )
        self.assertEqual(preview, result.rank_difference)
