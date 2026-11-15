"""Tier jumps: power jumps sharply on crossing into a new tier (#5093).

The standard ladder is 18 + 8 x (level - 1), one level 8 points wide, and a character's level
term is half her level's baseline. The seeded tiers start at levels 6, 11, 16, 21 and 26 and add
24 points each, three ranks at that width. So a level-6 character with ordinary skills (skills
supply the other half of her baseline) stands 4 ranks above a level-5 NPC, while a level-5
character stands 1 rank above a level-4 NPC.
"""

from decimal import Decimal
from importlib import import_module
from itertools import pairwise
from pathlib import Path

from django.test import TestCase

from world import migrations
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import ModifierLane
from world.checks.factories import CheckTypeFactory
from world.checks.modifier_models import LevelTier, ModifierLevelBaseline
from world.checks.modifier_values import (
    level_width,
    load_tier_table,
    rank_band_share,
    tier_bonus,
)
from world.checks.scale_config import CheckScaleConfig
from world.checks.services import (
    compute_obstacle_rating,
    compute_resist_increment,
    difficulty_level_for_points,
    difficulty_points,
    difficulty_step_points,
    level_opposition,
    level_points,
)
from world.checks.slide import band_position, load_ranks
from world.checks.test_helpers import make_player_character
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.seeds.modifier_values import seed_level_tiers
from world.traits.factories import ensure_level_ladder
from world.traits.models import CheckRank

_TIER_STARTS = (6, 11, 16, 21, 26)


def _make_tiers() -> None:
    for start_level in _TIER_STARTS:
        LevelTier.objects.create(start_level=start_level, bonus_points=24)


def _ordinary_skills(level: int) -> int:
    """The points skills and stats supply: the share of her baseline the level term leaves."""
    return 18 + 8 * (level - 1) - round(Decimal("0.5") * (18 + 8 * (level - 1)))


def _ordinary_total(level: int) -> int:
    """A level's character with ordinary skills: her level term plus what skills supply."""
    return level_points(level) + _ordinary_skills(level)


class TierBonusTests(TestCase):
    """U-keep: pure tier-sum math and loaded-table query counts, with no player seam of its own."""

    @classmethod
    def setUpTestData(cls) -> None:
        ensure_level_ladder()
        CheckScaleConfig.objects.update_or_create(pk=1, defaults={"level_share": Decimal("0.5")})
        _make_tiers()

    def test_the_bonus_is_the_sum_of_the_tiers_reached(self) -> None:
        self.assertEqual(tier_bonus(1), 0)
        self.assertEqual(tier_bonus(5), 0)
        self.assertEqual(tier_bonus(6), 24)
        self.assertEqual(tier_bonus(10), 24)
        self.assertEqual(tier_bonus(11), 48)
        self.assertEqual(tier_bonus(30), 120)
        self.assertEqual(tier_bonus(45), 120)

    def test_each_tier_is_its_own_row(self) -> None:
        tier = LevelTier.objects.get(start_level=11)
        tier.bonus_points = 40
        tier.save()
        self.assertEqual(tier_bonus(10), 24)
        self.assertEqual(tier_bonus(11), 64)
        self.assertEqual(tier_bonus(30), 136)

    def test_the_tiers_load_in_one_query(self) -> None:
        with self.assertNumQueries(1):
            table = load_tier_table()
        self.assertEqual(table.bonus(16), 72)

    def test_a_loaded_table_answers_without_a_query(self) -> None:
        table = load_tier_table()
        with self.assertNumQueries(0):
            self.assertEqual(tier_bonus(26, table), 120)

    def test_a_tier_does_not_change_the_width(self) -> None:
        self.assertEqual(level_width(5), 8)
        self.assertEqual(level_width(6), 8)
        self.assertEqual(difficulty_step_points(10, 5), difficulty_step_points(10, 6))

    def test_the_level_term_adds_the_bonus_in_full(self) -> None:
        # Half of level 5's 50 is 25 and half of level 6's 58 is 29; the 24 is not halved.
        self.assertEqual(level_points(5), 25)
        self.assertEqual(level_points(6), 29 + 24)
        self.assertEqual(level_points(0), 0)

    def test_an_npc_and_a_staff_set_difficulty_read_the_level_plus_its_tier(self) -> None:
        check_type = CheckTypeFactory(name="TierNpcCheck")
        self.assertEqual(level_opposition(check_type, level=5), 50)
        self.assertEqual(level_opposition(check_type, level=6), 58 + 24)
        self.assertEqual(difficulty_points(5), 50)
        self.assertEqual(difficulty_points(6), 58 + 24)
        self.assertEqual(difficulty_points(0), 0)

    def test_a_difficulty_level_round_trips_through_its_points(self) -> None:
        for level in range(1, 31):
            self.assertEqual(difficulty_level_for_points(difficulty_points(level)), level)

    def test_points_between_two_tiered_levels_read_the_nearer_one(self) -> None:
        # Level 5 is 50 points and level 6 is 82, so 65 is nearer 5 and 67 is nearer 6.
        self.assertEqual(difficulty_level_for_points(65), 5)
        self.assertEqual(difficulty_level_for_points(66), 5)
        self.assertEqual(difficulty_level_for_points(67), 6)

    def test_a_same_level_character_with_ordinary_skills_is_even_with_the_npc(self) -> None:
        check_type = CheckTypeFactory(name="TierEvenCheck")
        for level in (5, 6, 11, 26, 30):
            self.assertEqual(
                _ordinary_total(level), level_opposition(check_type, level=level), level
            )


class PlayerObstacleTierTests(TestCase):
    """U-keep: obstacle and resist ratings no journey drives.

    A player character who is the obstacle gets the tier once, through her level term."""

    @classmethod
    def setUpTestData(cls) -> None:
        ensure_level_ladder()
        CheckScaleConfig.objects.update_or_create(pk=1, defaults={"level_share": Decimal("0.5")})
        _make_tiers()
        cls.check_type = CheckTypeFactory(name="TierObstacleCheck")
        CheckTypeFactory(name="Composure")
        character_class = CharacterClassFactory()
        cls.fives = cls._player(character_class, 5)
        cls.sixes = cls._player(character_class, 6)

    @staticmethod
    def _player(character_class, level):
        sheet = make_player_character(CharacterSheetFactory())
        CharacterClassLevelFactory(
            character=sheet, character_class=character_class, level=level, is_primary=True
        )
        return sheet.character

    def test_the_obstacle_rating_is_her_level_term_and_nothing_added_twice(self) -> None:
        # No traits or modifiers: her rating is her level term alone, tier bonus included.
        self.assertEqual(compute_obstacle_rating(self.fives, self.check_type), 25)
        self.assertEqual(compute_obstacle_rating(self.sixes, self.check_type), 29 + 24)

    def test_the_rising_tier_adds_exactly_its_bonus_over_the_plain_step(self) -> None:
        step = compute_obstacle_rating(self.sixes, self.check_type) - compute_obstacle_rating(
            self.fives, self.check_type
        )
        self.assertEqual(step, level_points(6) - level_points(5))
        self.assertEqual(step, (29 - 25) + 24)

    def test_the_resist_increment_counts_the_tier_once(self) -> None:
        resist_five = compute_resist_increment(self.fives, "medium")
        resist_six = compute_resist_increment(self.sixes, "medium")
        self.assertEqual(resist_six - resist_five, (29 - 25) + 24)


class TierLadderTests(TestCase):
    """U-keep: ladder extension past rank 30 and rank naming, which a journey cannot reach."""

    @classmethod
    def setUpTestData(cls) -> None:
        ensure_level_ladder()
        _make_tiers()

    def test_the_ladder_runs_past_rank_thirty_evenly_spaced(self) -> None:
        # Level 30's baseline 250 plus 120 is 370, fifteen 8-point ranks above rank 30.
        ranks = load_ranks()
        by_rank = {step.rank: step for step in ranks}
        self.assertEqual(ranks[-1].rank, 45)
        self.assertEqual(by_rank[30].min_points, 250)
        self.assertEqual(by_rank[31].min_points, 258)
        self.assertEqual(by_rank[45].min_points, 370)
        self.assertGreaterEqual(ranks[-1].min_points, tier_bonus(30) + 250)
        gaps = {later.min_points - earlier.min_points for earlier, later in pairwise(ranks[1:])}
        self.assertEqual(gaps, {8})

    def test_a_rank_without_an_authored_row_is_named_by_its_number(self) -> None:
        by_rank = {step.rank: step.name for step in load_ranks()}
        self.assertEqual(by_rank[30], "Rank 30")
        self.assertEqual(by_rank[38], "Rank 38")
        self.assertFalse(CheckRank.objects.filter(rank__gt=30).exists())

    def test_a_row_the_staff_named_keeps_its_name(self) -> None:
        rank = CheckRank.objects.get(rank=30)
        rank.name = "Mythic"
        rank.save()
        by_rank = {step.rank: step.name for step in load_ranks()}
        self.assertEqual(by_rank[30], "Mythic")
        self.assertEqual(by_rank[31], "Rank 31")

    def test_a_total_above_the_old_top_is_a_higher_rank(self) -> None:
        position = band_position(262)
        self.assertEqual(position.rank.rank, 31)
        self.assertEqual(position.share, 0.5)
        self.assertEqual(position.text, "Rank 31, 50% toward Rank 32")
        top = band_position(370)
        self.assertEqual(top.rank.rank, 45)
        self.assertIsNone(top.next_rank)
        self.assertEqual(top.text, "Rank 45")

    def test_rank_for_points_and_difference_read_the_extended_ladder(self) -> None:
        self.assertEqual(CheckRank.get_rank_for_points(370).rank, 45)
        self.assertEqual(CheckRank.get_rank_for_points(369).rank, 44)
        self.assertEqual(CheckRank.get_rank_difference(370, 250), 15)

    def test_a_band_share_above_rank_thirty_still_reads_a_width(self) -> None:
        self.assertEqual(rank_band_share(4, 370), Decimal("0.50"))
        self.assertEqual(rank_band_share(4, 262), Decimal("0.50"))

    def test_the_bonus_does_not_lift_a_tier_start_off_the_ladder(self) -> None:
        # Level 6's strength is 82, which is where rank 9 starts: 58 + three ranks.
        self.assertEqual(band_position(58 + 24).rank.rank, 9)
        self.assertEqual(band_position(58 + 24).share, 0.0)


class NoTiersTests(TestCase):
    """U-keep: the empty-tier edge, which journeys never build since they seed tiers.

    With no ``LevelTier`` rows nothing changes: no jump and the ladder ends at 30."""

    @classmethod
    def setUpTestData(cls) -> None:
        ensure_level_ladder()
        CheckScaleConfig.objects.update_or_create(pk=1, defaults={"level_share": Decimal("0.5")})

    def test_the_bonus_is_zero_everywhere(self) -> None:
        self.assertEqual(tier_bonus(1), 0)
        self.assertEqual(tier_bonus(30), 0)

    def test_levels_read_their_plain_baselines(self) -> None:
        check_type = CheckTypeFactory(name="NoTierCheck")
        self.assertEqual(level_points(6), 29)
        self.assertEqual(level_opposition(check_type, level=6), 58)
        self.assertEqual(difficulty_points(6), 58)
        self.assertEqual(difficulty_level_for_points(58), 6)

    def test_the_ladder_still_ends_at_rank_thirty(self) -> None:
        ranks = load_ranks()
        self.assertEqual(len(ranks), 31)
        self.assertEqual(ranks[-1].rank, 30)

    def test_a_tier_alone_with_no_baselines_adds_nothing(self) -> None:
        ModifierLevelBaseline.objects.filter(lane=ModifierLane.CHECK).delete()
        _make_tiers()
        self.assertEqual(level_points(6), 0)
        self.assertEqual(difficulty_points(6), 0)


class LevelTierSeedAndMigrationTests(TestCase):
    """U-keep: a seed and a data migration, which no journey runs."""

    def test_the_seed_writes_a_level_three_row_at_zero_and_five_tiers_of_twenty_four(self) -> None:
        seed_level_tiers()
        self.assertEqual(
            list(LevelTier.objects.values_list("start_level", "bonus_points")),
            [(3, 0), (6, 24), (11, 24), (16, 24), (21, 24), (26, 24)],
        )

    def test_the_seed_leaves_tiers_staff_already_own(self) -> None:
        # Staff moved the level-11 tier to 12: a re-seed must not add a second jump at 11.
        LevelTier.objects.create(start_level=12, bonus_points=40)
        seed_level_tiers()
        self.assertEqual(
            list(LevelTier.objects.values_list("start_level", "bonus_points")), [(12, 40)]
        )

    @staticmethod
    def _run_migration() -> None:
        from django.apps import apps

        # Found by suffix, so a renumbering of the migration does not break the test.
        name = next(
            path.stem for path in Path(migrations.__file__).parent.glob("*_level_tier_rows.py")
        )
        import_module(f"world.migrations.{name}").write_tier_rows(apps, None)

    def test_a_database_with_check_baselines_gets_the_tiers(self) -> None:
        ensure_level_ladder()

        self._run_migration()

        self.assertEqual(
            list(LevelTier.objects.values_list("start_level", "bonus_points")),
            [(3, 0), (6, 24), (11, 24), (16, 24), (21, 24), (26, 24)],
        )

    def test_a_database_that_already_has_tiers_is_left_alone(self) -> None:
        ensure_level_ladder()
        LevelTier.objects.create(start_level=7, bonus_points=30)

        self._run_migration()

        self.assertEqual(
            list(LevelTier.objects.values_list("start_level", "bonus_points")), [(7, 30)]
        )

    def test_a_database_without_check_baselines_is_left_for_the_seeds(self) -> None:
        self._run_migration()

        self.assertFalse(LevelTier.objects.exists())
