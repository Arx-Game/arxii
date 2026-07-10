from django.core.exceptions import ValidationError
from django.test import TestCase

from world.achievements.factories import AchievementFactory
from world.codex.factories import CodexEntryFactory
from world.conditions.factories import ConditionTemplateFactory
from world.societies.factories import OrganizationFactory, SocietyFactory
from world.stories.constants import (
    BeatOutcome,
    BeatPredicateType,
    BeatVisibility,
    StoryMilestoneType,
)
from world.stories.factories import BeatFactory, ChapterFactory, EpisodeFactory, StoryFactory
from world.stories.models import Beat


class BeatTests(TestCase):
    def test_default_beat_is_gm_marked(self):
        beat = BeatFactory()
        self.assertEqual(beat.predicate_type, BeatPredicateType.GM_MARKED)
        self.assertEqual(beat.outcome, BeatOutcome.UNSATISFIED)
        self.assertEqual(beat.visibility, BeatVisibility.HINTED)

    def test_character_level_beat_requires_required_level(self):
        episode = EpisodeFactory()
        beat = BeatFactory.build(
            episode=episode,
            predicate_type=BeatPredicateType.CHARACTER_LEVEL_AT_LEAST,
            required_level=None,
        )
        with self.assertRaises(ValidationError):
            beat.full_clean()

    def test_gm_marked_beat_rejects_required_level(self):
        episode = EpisodeFactory()
        beat = BeatFactory.build(
            episode=episode,
            predicate_type=BeatPredicateType.GM_MARKED,
            required_level=5,
        )
        with self.assertRaises(ValidationError):
            beat.full_clean()

    def test_beat_text_layers(self):
        beat = BeatFactory(
            internal_description="Real predicate: research project X",
            player_hint="Something about the night...",
            player_resolution_text="You learned the truth.",
        )
        self.assertIn("X", beat.internal_description)
        self.assertIn("night", beat.player_hint)
        self.assertIn("truth", beat.player_resolution_text)

    # --- ACHIEVEMENT_HELD invariants ---

    def test_achievement_held_beat_requires_required_achievement(self):
        episode = EpisodeFactory()
        beat = BeatFactory.build(
            episode=episode,
            predicate_type=BeatPredicateType.ACHIEVEMENT_HELD,
            required_achievement=None,
        )
        with self.assertRaises(ValidationError):
            beat.full_clean()

    def test_gm_marked_beat_rejects_required_achievement(self):
        episode = EpisodeFactory()
        achievement = AchievementFactory()
        beat = BeatFactory.build(
            episode=episode,
            predicate_type=BeatPredicateType.GM_MARKED,
            required_achievement=achievement,
        )
        with self.assertRaises(ValidationError):
            beat.full_clean()

    def test_character_level_beat_rejects_required_achievement(self):
        episode = EpisodeFactory()
        achievement = AchievementFactory()
        beat = BeatFactory.build(
            episode=episode,
            predicate_type=BeatPredicateType.CHARACTER_LEVEL_AT_LEAST,
            required_level=5,
            required_achievement=achievement,
        )
        with self.assertRaises(ValidationError):
            beat.full_clean()

    # --- CONDITION_HELD invariants ---

    def test_condition_held_beat_requires_required_condition_template(self):
        episode = EpisodeFactory()
        beat = BeatFactory.build(
            episode=episode,
            predicate_type=BeatPredicateType.CONDITION_HELD,
            required_condition_template=None,
        )
        with self.assertRaises(ValidationError):
            beat.full_clean()

    def test_gm_marked_beat_rejects_required_condition_template(self):
        episode = EpisodeFactory()
        template = ConditionTemplateFactory()
        beat = BeatFactory.build(
            episode=episode,
            predicate_type=BeatPredicateType.GM_MARKED,
            required_condition_template=template,
        )
        with self.assertRaises(ValidationError):
            beat.full_clean()

    def test_achievement_held_beat_rejects_required_condition_template(self):
        episode = EpisodeFactory()
        achievement = AchievementFactory()
        template = ConditionTemplateFactory()
        beat = BeatFactory.build(
            episode=episode,
            predicate_type=BeatPredicateType.ACHIEVEMENT_HELD,
            required_achievement=achievement,
            required_condition_template=template,
        )
        with self.assertRaises(ValidationError):
            beat.full_clean()

    # --- CODEX_ENTRY_UNLOCKED invariants ---

    def test_codex_entry_unlocked_beat_requires_required_codex_entry(self):
        episode = EpisodeFactory()
        beat = BeatFactory.build(
            episode=episode,
            predicate_type=BeatPredicateType.CODEX_ENTRY_UNLOCKED,
            required_codex_entry=None,
        )
        with self.assertRaises(ValidationError):
            beat.full_clean()

    def test_gm_marked_beat_rejects_required_codex_entry(self):
        episode = EpisodeFactory()
        entry = CodexEntryFactory()
        beat = BeatFactory.build(
            episode=episode,
            predicate_type=BeatPredicateType.GM_MARKED,
            required_codex_entry=entry,
        )
        with self.assertRaises(ValidationError):
            beat.full_clean()

    def test_condition_held_beat_rejects_required_codex_entry(self):
        episode = EpisodeFactory()
        template = ConditionTemplateFactory()
        entry = CodexEntryFactory()
        beat = BeatFactory.build(
            episode=episode,
            predicate_type=BeatPredicateType.CONDITION_HELD,
            required_condition_template=template,
            required_codex_entry=entry,
        )
        with self.assertRaises(ValidationError):
            beat.full_clean()

    # --- STORY_AT_MILESTONE invariants ---

    def test_story_at_milestone_requires_referenced_story(self):
        episode = EpisodeFactory()
        beat = BeatFactory.build(
            episode=episode,
            predicate_type=BeatPredicateType.STORY_AT_MILESTONE,
            referenced_story=None,
            referenced_milestone_type=StoryMilestoneType.STORY_RESOLVED,
        )
        with self.assertRaises(ValidationError):
            beat.full_clean()

    def test_story_at_milestone_requires_referenced_milestone_type(self):
        episode = EpisodeFactory()
        story = StoryFactory()
        beat = BeatFactory.build(
            episode=episode,
            predicate_type=BeatPredicateType.STORY_AT_MILESTONE,
            referenced_story=story,
            referenced_milestone_type="",  # missing
        )
        with self.assertRaises(ValidationError):
            beat.full_clean()

    def test_chapter_reached_requires_referenced_chapter(self):
        episode = EpisodeFactory()
        story = StoryFactory()
        beat = BeatFactory.build(
            episode=episode,
            predicate_type=BeatPredicateType.STORY_AT_MILESTONE,
            referenced_story=story,
            referenced_milestone_type=StoryMilestoneType.CHAPTER_REACHED,
            referenced_chapter=None,
        )
        with self.assertRaises(ValidationError):
            beat.full_clean()

    def test_episode_reached_requires_referenced_episode(self):
        episode = EpisodeFactory()
        story = StoryFactory()
        beat = BeatFactory.build(
            episode=episode,
            predicate_type=BeatPredicateType.STORY_AT_MILESTONE,
            referenced_story=story,
            referenced_milestone_type=StoryMilestoneType.EPISODE_REACHED,
            referenced_episode=None,
        )
        with self.assertRaises(ValidationError):
            beat.full_clean()

    def test_story_resolved_rejects_referenced_chapter(self):
        episode = EpisodeFactory()
        story = StoryFactory()
        chapter = ChapterFactory(story=story)
        beat = BeatFactory.build(
            episode=episode,
            predicate_type=BeatPredicateType.STORY_AT_MILESTONE,
            referenced_story=story,
            referenced_milestone_type=StoryMilestoneType.STORY_RESOLVED,
            referenced_chapter=chapter,
        )
        with self.assertRaises(ValidationError):
            beat.full_clean()

    def test_story_resolved_rejects_referenced_episode(self):
        episode = EpisodeFactory()
        story = StoryFactory()
        ref_episode = EpisodeFactory()
        beat = BeatFactory.build(
            episode=episode,
            predicate_type=BeatPredicateType.STORY_AT_MILESTONE,
            referenced_story=story,
            referenced_milestone_type=StoryMilestoneType.STORY_RESOLVED,
            referenced_episode=ref_episode,
        )
        with self.assertRaises(ValidationError):
            beat.full_clean()

    def test_non_milestone_predicate_rejects_referenced_story(self):
        episode = EpisodeFactory()
        story = StoryFactory()
        beat = BeatFactory.build(
            episode=episode,
            predicate_type=BeatPredicateType.GM_MARKED,
            referenced_story=story,
        )
        with self.assertRaises(ValidationError):
            beat.full_clean()

    # --- AGGREGATE_THRESHOLD invariants ---

    def test_clean_rejects_aggregate_without_required_points(self):
        """AGGREGATE_THRESHOLD with required_points=None raises ValidationError."""
        episode = EpisodeFactory()
        beat = BeatFactory.build(
            episode=episode,
            predicate_type=BeatPredicateType.AGGREGATE_THRESHOLD,
            required_points=None,
        )
        with self.assertRaises(ValidationError):
            beat.full_clean()

    def test_clean_rejects_non_aggregate_with_required_points(self):
        """GM_MARKED with required_points set raises ValidationError."""
        episode = EpisodeFactory()
        beat = BeatFactory.build(
            episode=episode,
            predicate_type=BeatPredicateType.GM_MARKED,
            required_points=100,
        )
        with self.assertRaises(ValidationError):
            beat.full_clean()

    def test_aggregate_threshold_valid_with_required_points(self):
        """AGGREGATE_THRESHOLD with required_points passes validation."""
        episode = EpisodeFactory()
        beat = BeatFactory.build(
            episode=episode,
            predicate_type=BeatPredicateType.AGGREGATE_THRESHOLD,
            required_points=50,
        )
        # Should not raise.
        beat.full_clean()

    # --- FACTION_STANDING_AT_LEAST invariants ---

    def test_faction_standing_predicate_requires_exactly_one_of_society_org(self) -> None:
        from world.societies.factories import SocietyFactory

        episode = EpisodeFactory()
        society = SocietyFactory()
        beat = BeatFactory.build(
            episode=episode,
            predicate_type=BeatPredicateType.FACTION_STANDING_AT_LEAST,
            required_society=society,
            required_standing=100,
        )
        beat.full_clean()  # must not raise: exactly one of society/org set

    def test_faction_standing_predicate_rejects_neither_society_nor_org(self) -> None:
        episode = EpisodeFactory()
        beat = BeatFactory.build(
            episode=episode,
            predicate_type=BeatPredicateType.FACTION_STANDING_AT_LEAST,
            required_standing=100,
        )
        with self.assertRaises(ValidationError):
            beat.full_clean()

    def test_faction_standing_predicate_rejects_both_society_and_org(self) -> None:
        episode = EpisodeFactory()
        beat = BeatFactory.build(
            episode=episode,
            predicate_type=BeatPredicateType.FACTION_STANDING_AT_LEAST,
            required_society=SocietyFactory(),
            required_organization=OrganizationFactory(),
            required_standing=100,
        )
        with self.assertRaises(ValidationError):
            beat.full_clean()


class BeatSetNullOnDeleteTests(TestCase):
    """Beat's predicate-config FKs use SET_NULL, not CASCADE (#1796).

    A Beat is story-significant: deleting its config target must null the FK
    rather than erase the beat. The beat becomes permanently UNSATISFIED
    (evaluators return UNSATISFIED for a nulled config FK).

    SharedMemoryModel's identity map caches FK values in-memory after first
    access, so ``refresh_from_db()`` may still return the cached object. We
    read the persisted FK id directly via ``values_list`` (same pattern as
    ``test_models_required_mission.py``).
    """

    def test_achievement_held_survives_achievement_delete(self) -> None:
        beat = BeatFactory(
            predicate_type=BeatPredicateType.ACHIEVEMENT_HELD,
            required_achievement=AchievementFactory(),
        )
        beat_pk = beat.pk
        beat.required_achievement.delete()

        fk_id = (
            Beat.objects.filter(pk=beat_pk)
            .values_list("required_achievement_id", flat=True)
            .first()
        )
        self.assertIsNone(fk_id)
        self.assertEqual(Beat.objects.get(pk=beat_pk).outcome, BeatOutcome.UNSATISFIED)

    def test_condition_held_survives_condition_template_delete(self) -> None:
        beat = BeatFactory(
            predicate_type=BeatPredicateType.CONDITION_HELD,
            required_condition_template=ConditionTemplateFactory(),
        )
        beat_pk = beat.pk
        beat.required_condition_template.delete()

        fk_id = (
            Beat.objects.filter(pk=beat_pk)
            .values_list("required_condition_template_id", flat=True)
            .first()
        )
        self.assertIsNone(fk_id)
        self.assertEqual(Beat.objects.get(pk=beat_pk).outcome, BeatOutcome.UNSATISFIED)

    def test_codex_entry_unlocked_survives_codex_entry_delete(self) -> None:
        beat = BeatFactory(
            predicate_type=BeatPredicateType.CODEX_ENTRY_UNLOCKED,
            required_codex_entry=CodexEntryFactory(),
        )
        beat_pk = beat.pk
        beat.required_codex_entry.delete()

        fk_id = (
            Beat.objects.filter(pk=beat_pk)
            .values_list("required_codex_entry_id", flat=True)
            .first()
        )
        self.assertIsNone(fk_id)
        self.assertEqual(Beat.objects.get(pk=beat_pk).outcome, BeatOutcome.UNSATISFIED)

    def test_story_at_milestone_survives_referenced_story_delete(self) -> None:
        story = StoryFactory()
        beat = BeatFactory(
            predicate_type=BeatPredicateType.STORY_AT_MILESTONE,
            referenced_story=story,
            referenced_milestone_type=StoryMilestoneType.STORY_RESOLVED,
        )
        beat_pk = beat.pk
        story.delete()

        fk_id = (
            Beat.objects.filter(pk=beat_pk).values_list("referenced_story_id", flat=True).first()
        )
        self.assertIsNone(fk_id)
        self.assertEqual(Beat.objects.get(pk=beat_pk).outcome, BeatOutcome.UNSATISFIED)

    def test_story_at_milestone_survives_referenced_chapter_delete(self) -> None:
        story = StoryFactory()
        chapter = ChapterFactory(story=story)
        beat = BeatFactory(
            predicate_type=BeatPredicateType.STORY_AT_MILESTONE,
            referenced_story=story,
            referenced_milestone_type=StoryMilestoneType.CHAPTER_REACHED,
            referenced_chapter=chapter,
        )
        beat_pk = beat.pk
        chapter.delete()

        fk_id = (
            Beat.objects.filter(pk=beat_pk).values_list("referenced_chapter_id", flat=True).first()
        )
        self.assertIsNone(fk_id)
        self.assertEqual(Beat.objects.get(pk=beat_pk).outcome, BeatOutcome.UNSATISFIED)

    def test_story_at_milestone_survives_referenced_episode_delete(self) -> None:
        story = StoryFactory()
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        beat = BeatFactory(
            predicate_type=BeatPredicateType.STORY_AT_MILESTONE,
            referenced_story=story,
            referenced_milestone_type=StoryMilestoneType.EPISODE_REACHED,
            referenced_episode=episode,
        )
        beat_pk = beat.pk
        episode.delete()

        fk_id = (
            Beat.objects.filter(pk=beat_pk).values_list("referenced_episode_id", flat=True).first()
        )
        self.assertIsNone(fk_id)
        self.assertEqual(Beat.objects.get(pk=beat_pk).outcome, BeatOutcome.UNSATISFIED)

    def test_faction_standing_survives_society_delete(self) -> None:
        beat = BeatFactory(
            predicate_type=BeatPredicateType.FACTION_STANDING_AT_LEAST,
            required_society=SocietyFactory(),
            required_standing=100,
        )
        beat_pk = beat.pk
        beat.required_society.delete()

        fk_id = (
            Beat.objects.filter(pk=beat_pk).values_list("required_society_id", flat=True).first()
        )
        self.assertIsNone(fk_id)
        self.assertEqual(Beat.objects.get(pk=beat_pk).outcome, BeatOutcome.UNSATISFIED)

    def test_faction_standing_survives_organization_delete(self) -> None:
        beat = BeatFactory(
            predicate_type=BeatPredicateType.FACTION_STANDING_AT_LEAST,
            required_organization=OrganizationFactory(),
            required_standing=100,
        )
        beat_pk = beat.pk
        beat.required_organization.delete()

        fk_id = (
            Beat.objects.filter(pk=beat_pk)
            .values_list("required_organization_id", flat=True)
            .first()
        )
        self.assertIsNone(fk_id)
        self.assertEqual(Beat.objects.get(pk=beat_pk).outcome, BeatOutcome.UNSATISFIED)
