"""Tests for promote_gm (audit-writing level change) + gm_evidence_summary."""

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.gm.models import GMLevelChange
from world.gm.services import gm_evidence_summary, promote_gm
from world.societies.constants import RenownRisk
from world.stories.factories import (
    BeatCompletionFactory,
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    StoryFactory,
    StoryFeedbackFactory,
    TrustCategoryFactory,
    TrustCategoryFeedbackRatingFactory,
)


class PromoteGmTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory()

    def test_writes_level_and_audit_row(self) -> None:
        profile = GMProfileFactory(level=GMLevel.STARTING)

        change = promote_gm(
            profile,
            GMLevel.JUNIOR,
            changed_by=self.staff,
            reason="Ran three tables well.",
        )

        profile.refresh_from_db()
        assert profile.level == GMLevel.JUNIOR
        assert isinstance(change, GMLevelChange)
        assert change.profile_id == profile.pk
        assert change.old_level == GMLevel.STARTING
        assert change.new_level == GMLevel.JUNIOR
        assert change.changed_by == self.staff
        assert change.reason == "Ran three tables well."
        assert GMLevelChange.objects.filter(pk=change.pk).exists()

    def test_demotion_writes_audit_row(self) -> None:
        profile = GMProfileFactory(level=GMLevel.GM)

        change = promote_gm(
            profile,
            GMLevel.JUNIOR,
            changed_by=self.staff,
            reason="Repeated table no-shows.",
        )

        profile.refresh_from_db()
        assert profile.level == GMLevel.JUNIOR
        assert change.old_level == GMLevel.GM
        assert change.new_level == GMLevel.JUNIOR

    def test_same_level_raises_value_error(self) -> None:
        profile = GMProfileFactory(level=GMLevel.STARTING)

        with self.assertRaises(ValueError):
            promote_gm(
                profile,
                GMLevel.STARTING,
                changed_by=self.staff,
                reason="No-op.",
            )
        assert not GMLevelChange.objects.filter(profile=profile).exists()

    def test_unknown_level_raises_value_error(self) -> None:
        profile = GMProfileFactory(level=GMLevel.STARTING)

        with self.assertRaises(ValueError):
            promote_gm(
                profile,
                "not-a-real-level",
                changed_by=self.staff,
                reason="Bogus.",
            )
        assert not GMLevelChange.objects.filter(profile=profile).exists()


class GmEvidenceSummaryTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory()

    def test_counts_seeded_beat_completion_and_feedback(self) -> None:
        profile = GMProfileFactory(level=GMLevel.GM)
        table = GMTableFactory(gm=profile)
        story = StoryFactory(primary_table=table)
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        beat = BeatFactory(episode=episode, risk=RenownRisk.MODERATE)
        BeatCompletionFactory(beat=beat)

        reviewer = AccountFactory()
        feedback = StoryFeedbackFactory(
            story=story,
            reviewer=reviewer,
            reviewed_player=profile.account,
        )
        category = TrustCategoryFactory(name="pacing")
        TrustCategoryFeedbackRatingFactory(
            feedback=feedback,
            trust_category=category,
            rating=2,
        )

        change = promote_gm(
            profile,
            GMLevel.EXPERIENCED,
            changed_by=self.staff,
            reason="Promotion for evidence test.",
        )

        summary = gm_evidence_summary(profile)

        assert summary.profile_id == profile.pk
        assert summary.level == GMLevel.EXPERIENCED
        assert summary.approved_at == profile.approved_at
        assert summary.last_active_at == profile.last_active_at
        assert summary.stories_running == 1
        assert summary.beats_completed_by_risk == {RenownRisk.MODERATE: 1}
        assert len(summary.feedback_by_category) == 1
        category_feedback = summary.feedback_by_category[0]
        assert category_feedback.category_name == "pacing"
        assert category_feedback.average_rating == 2.0
        assert category_feedback.rating_count == 1
        assert summary.level_changes == [change]

    def test_stories_running_excludes_inactive_table_or_story(self) -> None:
        from world.gm.constants import GMTableStatus
        from world.stories.types import StoryStatus

        profile = GMProfileFactory(level=GMLevel.GM)
        active_table = GMTableFactory(gm=profile)
        archived_table = GMTableFactory(gm=profile, status=GMTableStatus.ARCHIVED)
        StoryFactory(primary_table=active_table, status=StoryStatus.ACTIVE)
        StoryFactory(primary_table=active_table, status=StoryStatus.COMPLETED)
        StoryFactory(primary_table=archived_table, status=StoryStatus.ACTIVE)

        summary = gm_evidence_summary(profile)

        assert summary.stories_running == 1

    def test_no_evidence_returns_empty_aggregates(self) -> None:
        profile = GMProfileFactory(level=GMLevel.STARTING)

        summary = gm_evidence_summary(profile)

        assert summary.stories_running == 0
        assert summary.beats_completed_by_risk == {}
        assert summary.feedback_by_category == []
        assert summary.level_changes == []
