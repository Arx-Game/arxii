"""Tests for achievement service functions."""

from django.test import TestCase

from world.achievements.factories import (
    AchievementFactory,
    AchievementStatRequirementFactory,
    StatDefinitionFactory,
    StatTrackerFactory,
)
from world.achievements.models import CharacterAchievement, Discovery, StatTracker
from world.achievements.services import get_stat, grant_achievement, increment_stat
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import grant_test_tenure


class GetStatTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.stat_def = StatDefinitionFactory(key="kills", name="Kills")

    def test_returns_zero_for_nonexistent(self) -> None:
        nonexistent = StatDefinitionFactory(key="nonexistent_stat", name="Nonexistent")
        result = get_stat(self.sheet, nonexistent)
        self.assertEqual(result, 0)

    def test_returns_value_for_existing(self) -> None:
        StatTrackerFactory(character_sheet=self.sheet, stat=self.stat_def, value=42)
        result = get_stat(self.sheet, self.stat_def)
        self.assertEqual(result, 42)


class IncrementStatTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        grant_test_tenure(cls.sheet)
        cls.new_stat = StatDefinitionFactory(key="new_stat", name="New Stat")
        cls.combat_stat = StatDefinitionFactory(key="combat_wins", name="Combat Wins")
        cls.quest_stat = StatDefinitionFactory(key="quests", name="Quests")

    def test_creates_tracker_if_not_exists(self) -> None:
        result = increment_stat(self.sheet, self.new_stat)
        self.assertEqual(result, 1)
        self.assertTrue(
            StatTracker.objects.filter(character_sheet=self.sheet, stat=self.new_stat).exists()
        )

    def test_increments_existing_tracker(self) -> None:
        StatTrackerFactory(character_sheet=self.sheet, stat=self.combat_stat, value=5)
        result = increment_stat(self.sheet, self.combat_stat, amount=3)
        self.assertEqual(result, 8)

    def test_checks_achievements_after_increment(self) -> None:
        achievement = AchievementFactory()
        AchievementStatRequirementFactory(
            achievement=achievement, stat=self.quest_stat, threshold=10
        )
        StatTrackerFactory(character_sheet=self.sheet, stat=self.quest_stat, value=9)

        increment_stat(self.sheet, self.quest_stat, amount=1)

        self.assertTrue(
            CharacterAchievement.objects.filter(
                character_sheet=self.sheet, achievement=achievement
            ).exists()
        )

    def test_does_not_grant_if_threshold_not_met(self) -> None:
        achievement = AchievementFactory()
        AchievementStatRequirementFactory(
            achievement=achievement, stat=self.quest_stat, threshold=10
        )
        StatTrackerFactory(character_sheet=self.sheet, stat=self.quest_stat, value=5)

        increment_stat(self.sheet, self.quest_stat, amount=1)

        self.assertFalse(
            CharacterAchievement.objects.filter(
                character_sheet=self.sheet, achievement=achievement
            ).exists()
        )

    def test_does_not_grant_already_earned(self) -> None:
        achievement = AchievementFactory()
        AchievementStatRequirementFactory(
            achievement=achievement, stat=self.quest_stat, threshold=5
        )
        StatTrackerFactory(character_sheet=self.sheet, stat=self.quest_stat, value=9)

        increment_stat(self.sheet, self.quest_stat, amount=1)
        increment_stat(self.sheet, self.quest_stat, amount=1)

        self.assertEqual(
            CharacterAchievement.objects.filter(
                character_sheet=self.sheet, achievement=achievement
            ).count(),
            1,
        )

    def test_prerequisite_not_met_blocks_grant(self) -> None:
        tier1 = AchievementFactory(slug="tier1")
        AchievementStatRequirementFactory(achievement=tier1, stat=self.quest_stat, threshold=10)

        tier2 = AchievementFactory(slug="tier2", prerequisite=tier1)
        AchievementStatRequirementFactory(achievement=tier2, stat=self.quest_stat, threshold=10)

        StatTrackerFactory(character_sheet=self.sheet, stat=self.quest_stat, value=9)

        # This increment meets both thresholds. tier1 should grant first,
        # then tier2 should also grant since tier1 is now earned.
        increment_stat(self.sheet, self.quest_stat, amount=1)

        self.assertTrue(
            CharacterAchievement.objects.filter(
                character_sheet=self.sheet, achievement=tier1
            ).exists()
        )
        self.assertTrue(
            CharacterAchievement.objects.filter(
                character_sheet=self.sheet, achievement=tier2
            ).exists()
        )

    def test_inactive_achievement_not_granted(self) -> None:
        achievement = AchievementFactory(is_active=False)
        AchievementStatRequirementFactory(
            achievement=achievement, stat=self.quest_stat, threshold=1
        )
        StatTrackerFactory(character_sheet=self.sheet, stat=self.quest_stat, value=0)

        increment_stat(self.sheet, self.quest_stat, amount=1)

        self.assertFalse(
            CharacterAchievement.objects.filter(
                character_sheet=self.sheet, achievement=achievement
            ).exists()
        )


class GrantAchievementTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.achievement = AchievementFactory()
        cls.sheet1 = CharacterSheetFactory()
        cls.tenure1 = grant_test_tenure(cls.sheet1)
        cls.sheet2 = CharacterSheetFactory()
        cls.tenure2 = grant_test_tenure(cls.sheet2)

    def test_single_grant_creates_discovery(self) -> None:
        results = grant_achievement(self.achievement, [self.sheet1])

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].achievement, self.achievement)
        self.assertIsNotNone(results[0].discovery)
        self.assertTrue(Discovery.objects.filter(achievement=self.achievement).exists())

    def test_first_earner_discovery_carries_their_tenure(self) -> None:
        """#3055: the Discovery row anchors to the earning sheet's current tenure."""
        results = grant_achievement(self.achievement, [self.sheet1])

        discovery = results[0].discovery
        self.assertEqual(discovery.discovered_by_tenure_id, self.tenure1.pk)

    def test_batch_grant_shares_discovery(self) -> None:
        results = grant_achievement(self.achievement, [self.sheet1, self.sheet2])

        self.assertEqual(len(results), 2)
        self.assertEqual(Discovery.objects.filter(achievement=self.achievement).count(), 1)

        discovery = Discovery.objects.get(achievement=self.achievement)
        self.assertEqual(discovery.discoverers.count(), 2)

    def test_party_grant_discovery_slot_goes_to_first_sheet_tenure(self) -> None:
        """#3055: for a party grant, the Discovery slot anchors to the FIRST sheet
        in the list (the triggering sheet) -- co-earners still get
        CharacterAchievement rows, but no second Discovery is created for them."""
        results = grant_achievement(self.achievement, [self.sheet1, self.sheet2])

        discovery = Discovery.objects.get(achievement=self.achievement)
        self.assertEqual(discovery.discovered_by_tenure_id, self.tenure1.pk)
        self.assertEqual(len(results), 2)
        self.assertEqual(Discovery.objects.filter(achievement=self.achievement).count(), 1)
        # Simultaneous co-discoverers share the credit via the M2M (#3055 ruling).
        self.assertEqual(
            list(discovery.shared_with_tenures.values_list("pk", flat=True)),
            [self.tenure2.pk],
        )

    def test_solo_discovery_has_no_shared_tenures(self) -> None:
        """#3055: a solo first discovery leaves the shared-credit set empty."""
        grant_achievement(self.achievement, [self.sheet1])

        discovery = Discovery.objects.get(achievement=self.achievement)
        self.assertEqual(discovery.shared_with_tenures.count(), 0)

    def test_subsequent_grant_no_discovery(self) -> None:
        # First character gets discovery
        first_results = grant_achievement(self.achievement, [self.sheet1])
        self.assertIsNotNone(first_results[0].discovery)

        # Second character does not get a new discovery
        second_results = grant_achievement(self.achievement, [self.sheet2])
        self.assertIsNone(second_results[0].discovery)
        self.assertEqual(Discovery.objects.filter(achievement=self.achievement).count(), 1)

    def test_no_duplicate_grants(self) -> None:
        grant_achievement(self.achievement, [self.sheet1])
        grant_achievement(self.achievement, [self.sheet1])

        self.assertEqual(
            CharacterAchievement.objects.filter(
                character_sheet=self.sheet1, achievement=self.achievement
            ).count(),
            1,
        )


class GrantAchievementStoryReactivityTest(TestCase):
    """grant_achievement fires the stories reactivity hook on newly-earned rows."""

    def test_flips_character_scope_achievement_beat(self) -> None:
        from world.stories.constants import (
            BeatOutcome,
            BeatPredicateType,
            StoryScope,
        )
        from world.stories.factories import (
            BeatFactory,
            ChapterFactory,
            EpisodeFactory,
            StoryFactory,
            StoryProgressFactory,
        )
        from world.stories.models import BeatCompletion

        sheet = CharacterSheetFactory()
        grant_test_tenure(sheet)
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        episode = EpisodeFactory(chapter=ChapterFactory(story=story))
        StoryProgressFactory(
            story=story,
            character_sheet=sheet,
            current_episode=episode,
        )
        achievement = AchievementFactory()
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.ACHIEVEMENT_HELD,
            required_achievement=achievement,
            outcome=BeatOutcome.UNSATISFIED,
        )

        grant_achievement(achievement, [sheet])

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)
        self.assertTrue(
            BeatCompletion.objects.filter(beat=beat, character_sheet=sheet).exists(),
        )

    def test_duplicate_grant_does_not_refire_hook(self) -> None:
        """Re-granting an already-earned achievement doesn't create new
        BeatCompletion rows via the reactivity hook."""
        from world.stories.constants import (
            BeatOutcome,
            BeatPredicateType,
            StoryScope,
        )
        from world.stories.factories import (
            BeatFactory,
            ChapterFactory,
            EpisodeFactory,
            StoryFactory,
            StoryProgressFactory,
        )
        from world.stories.models import BeatCompletion

        sheet = CharacterSheetFactory()
        grant_test_tenure(sheet)
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        episode = EpisodeFactory(chapter=ChapterFactory(story=story))
        StoryProgressFactory(
            story=story,
            character_sheet=sheet,
            current_episode=episode,
        )
        achievement = AchievementFactory()
        BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.ACHIEVEMENT_HELD,
            required_achievement=achievement,
            outcome=BeatOutcome.UNSATISFIED,
        )

        grant_achievement(achievement, [sheet])
        count_after_first = BeatCompletion.objects.count()
        grant_achievement(achievement, [sheet])
        count_after_second = BeatCompletion.objects.count()
        self.assertEqual(count_after_first, count_after_second)


class AchievementEligibilityGateTest(TestCase):
    """#3024: only sheets piloted by a regular player may earn achievements."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.stat = StatDefinitionFactory(key="gate_stat", name="Gate Stat")
        cls.achievement = AchievementFactory(name="Gate Test", slug="gate-test")
        AchievementStatRequirementFactory(achievement=cls.achievement, stat=cls.stat, threshold=3)

    def test_untenured_sheet_stat_increment_never_grants(self) -> None:
        sheet = CharacterSheetFactory()
        for _ in range(5):
            increment_stat(sheet, self.stat)
        self.assertEqual(get_stat(sheet, self.stat), 5)  # tracking continues
        self.assertFalse(CharacterAchievement.objects.filter(character_sheet=sheet).exists())
        self.assertFalse(Discovery.objects.filter(achievement=self.achievement).exists())

    def test_staff_piloted_sheet_never_grants(self) -> None:
        from evennia_extensions.factories import AccountFactory
        from world.roster.factories import (
            PlayerDataFactory,
            RosterEntryFactory,
            RosterTenureFactory,
        )

        sheet = CharacterSheetFactory()
        RosterTenureFactory(
            roster_entry=RosterEntryFactory(character_sheet=sheet),
            player_data=PlayerDataFactory(account=AccountFactory(is_staff=True)),
            end_date=None,
        )
        for _ in range(5):
            increment_stat(sheet, self.stat)
        self.assertFalse(CharacterAchievement.objects.filter(character_sheet=sheet).exists())

    def test_grant_filters_mixed_co_discoverer_list(self) -> None:
        from world.roster.factories import grant_test_tenure

        eligible = CharacterSheetFactory()
        eligible_tenure = grant_test_tenure(eligible)
        ineligible = CharacterSheetFactory()
        results = grant_achievement(self.achievement, [eligible, ineligible])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].character_sheet, eligible)
        self.assertIsNotNone(results[0].discovery_id)
        self.assertEqual(results[0].discovery.discovered_by_tenure_id, eligible_tenure.pk)
        self.assertFalse(CharacterAchievement.objects.filter(character_sheet=ineligible).exists())

    def test_all_ineligible_grant_is_a_noop(self) -> None:
        sheet = CharacterSheetFactory()
        results = grant_achievement(self.achievement, [sheet])
        self.assertEqual(results, [])
        self.assertFalse(Discovery.objects.filter(achievement=self.achievement).exists())

    def test_npc_then_tenured_earns_on_next_increment(self) -> None:
        from world.roster.factories import grant_test_tenure

        sheet = CharacterSheetFactory()
        for _ in range(5):
            increment_stat(sheet, self.stat)  # accrues past threshold, no grant
        self.assertFalse(CharacterAchievement.objects.filter(character_sheet=sheet).exists())
        grant_test_tenure(sheet)
        increment_stat(sheet, self.stat)
        self.assertTrue(
            CharacterAchievement.objects.filter(
                character_sheet=sheet, achievement=self.achievement
            ).exists()
        )
