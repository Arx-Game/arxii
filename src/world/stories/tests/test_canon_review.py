"""Canon-impact review: impact tiers + staff review for world-touching content (#2003)."""

from django.db import IntegrityError
from django.test import TestCase
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory, seed_default_gm_level_caps
from world.societies.constants import RenownRisk
from world.stories.constants import (
    BeatOutcome,
    BeatPredicateType,
    CanonReviewStatus,
    ImpactTier,
    StakeResolutionColumn,
    StakeSeverity,
    StoryMaturity,
)
from world.stories.factories import (
    BeatFactory,
    EpisodeFactory,
    StakeFactory,
    StakeResolutionFactory,
    StakeRewardLineFactory,
    StoryFactory,
    TransitionFactory,
    seed_default_risk_calibrations,
)
from world.stories.models import Beat, CanonReview, Story, TransitionRequiredOutcome
from world.stories.services.canon_review import (
    _notify_story_owners,
    clear_canon_review,
    latest_review_for_story,
    pending_canon_reviews,
    regional_auto_clears,
    request_canon_review,
    request_changes,
    story_is_cleared,
)
from world.stories.services.stakes import validate_stakes_readiness


class ImpactTierFieldTests(TestCase):
    def test_story_defaults_to_table_tier(self) -> None:
        story = Story.objects.create(title="T", description="")
        self.assertEqual(story.impact_tier, ImpactTier.TABLE)

    def test_impact_tier_choices_round_trip(self) -> None:
        for tier in (ImpactTier.TABLE, ImpactTier.REGIONAL, ImpactTier.WORLD):
            story = Story.objects.create(title=f"Story {tier}", description="", impact_tier=tier)
            story.refresh_from_db()
            self.assertEqual(story.impact_tier, tier)


class CanonReviewModelTests(TestCase):
    def test_defaults_to_pending(self) -> None:
        story = Story.objects.create(title="T", description="", impact_tier=ImpactTier.WORLD)
        review = CanonReview.objects.create(story=story, tier=ImpactTier.WORLD)
        self.assertEqual(review.status, CanonReviewStatus.PENDING)
        self.assertIsNone(review.resolved_at)
        self.assertEqual(review.tier, ImpactTier.WORLD)

    def test_only_one_pending_review_per_story(self) -> None:
        story = Story.objects.create(title="T", description="", impact_tier=ImpactTier.WORLD)
        CanonReview.objects.create(story=story, tier=ImpactTier.WORLD)
        with self.assertRaises(IntegrityError):
            CanonReview.objects.create(story=story, tier=ImpactTier.WORLD)

    def test_cleared_review_allows_new_pending(self) -> None:
        story = Story.objects.create(title="T", description="", impact_tier=ImpactTier.WORLD)
        old = CanonReview.objects.create(story=story, tier=ImpactTier.WORLD)
        old.status = CanonReviewStatus.CLEARED
        old.save()
        # A new PENDING review is now allowed
        CanonReview.objects.create(story=story, tier=ImpactTier.WORLD)
        self.assertEqual(CanonReview.objects.filter(story=story).count(), 2)


class CanonReviewServiceTests(TestCase):
    def setUp(self) -> None:
        seed_default_gm_level_caps()

    def test_request_creates_pending_review(self) -> None:
        story = Story.objects.create(title="T", description="", impact_tier=ImpactTier.WORLD)
        review = request_canon_review(story)
        self.assertEqual(review.status, CanonReviewStatus.PENDING)
        self.assertEqual(review.tier, ImpactTier.WORLD)

    def test_request_is_idempotent_returns_existing_pending(self) -> None:
        story = Story.objects.create(title="T", description="", impact_tier=ImpactTier.WORLD)
        first = request_canon_review(story)
        second = request_canon_review(story)
        self.assertEqual(first.pk, second.pk)

    def test_clear_sets_cleared_and_resolved_at(self) -> None:
        staff = AccountFactory()
        story = Story.objects.create(title="T", description="", impact_tier=ImpactTier.WORLD)
        review = request_canon_review(story)
        cleared = clear_canon_review(review, staff, notes="ok")
        self.assertEqual(cleared.status, CanonReviewStatus.CLEARED)
        self.assertIsNotNone(cleared.resolved_at)
        self.assertEqual(cleared.reviewer, staff)

    def test_request_changes_sets_status_and_notes(self) -> None:
        staff = AccountFactory()
        story = Story.objects.create(title="T", description="", impact_tier=ImpactTier.WORLD)
        review = request_canon_review(story)
        changed = request_changes(review, staff, notes="narrow scope")
        self.assertEqual(changed.status, CanonReviewStatus.CHANGES_REQUESTED)
        self.assertIn("narrow scope", changed.notes)

    def test_story_is_cleared_true_after_clear(self) -> None:
        staff = AccountFactory()
        story = Story.objects.create(title="T", description="", impact_tier=ImpactTier.WORLD)
        review = request_canon_review(story)
        clear_canon_review(review, staff)
        self.assertTrue(story_is_cleared(story))

    def test_story_is_cleared_false_when_pending(self) -> None:
        story = Story.objects.create(title="T", description="", impact_tier=ImpactTier.WORLD)
        request_canon_review(story)
        self.assertFalse(story_is_cleared(story))

    def test_regional_auto_clears_for_experienced(self) -> None:
        gm = GMProfileFactory(level=GMLevel.EXPERIENCED)
        self.assertTrue(regional_auto_clears(gm))

    def test_regional_auto_clears_false_for_junior(self) -> None:
        gm = GMProfileFactory(level=GMLevel.JUNIOR)
        self.assertFalse(regional_auto_clears(gm))

    def test_pending_canon_reviews_lists_only_pending(self) -> None:
        staff = AccountFactory()
        s1 = Story.objects.create(title="A", description="", impact_tier=ImpactTier.WORLD)
        s2 = Story.objects.create(title="B", description="", impact_tier=ImpactTier.WORLD)
        r1 = request_canon_review(s1)
        r2 = request_canon_review(s2)
        clear_canon_review(r2, staff)
        ids = list(pending_canon_reviews().values_list("pk", flat=True))
        self.assertIn(r1.pk, ids)
        self.assertNotIn(r2.pk, ids)

    def test_latest_review_for_story_returns_most_recent(self) -> None:
        staff = AccountFactory()
        story = Story.objects.create(title="T", description="", impact_tier=ImpactTier.WORLD)
        old = request_canon_review(story)
        clear_canon_review(old, staff, notes="first pass")
        newer = request_canon_review(story)
        self.assertEqual(latest_review_for_story(story).pk, newer.pk)

    def test_clear_non_pending_raises(self) -> None:
        staff = AccountFactory()
        story = Story.objects.create(title="T", description="", impact_tier=ImpactTier.WORLD)
        review = request_canon_review(story)
        clear_canon_review(review, staff)
        with self.assertRaises(ValueError):
            clear_canon_review(review, staff)


class CanonReviewReadinessIntegrationTests(TestCase):
    """WORLD unreviewed -> UNREADY -> effective NONE; CLEARED -> pays (spec tests).

    Mirrors ValidateStakesReadinessTests' ready-shape so the ONLY blocker is the
    canon-review gate (#2003). validate_stakes_readiness is the seam where an
    unreviewed WORLD-tier story's staked beats become UNREADY (effective NONE).
    """

    @classmethod
    def setUpTestData(cls) -> None:
        seed_default_risk_calibrations()

    def _ready_world_beat(self) -> Beat:
        """A HIGH beat on a WORLD-tier story that clears every readiness rule
        EXCEPT the canon-review gate (which this test toggles)."""
        story = StoryFactory(impact_tier=ImpactTier.WORLD)
        beat = BeatFactory(
            episode__chapter__story=story,
            risk=RenownRisk.HIGH,
            target_level=4,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
        )
        # DIRE stake (total 4 = HIGH floor) + WIN/LOSS columns authored.
        stake = StakeFactory(beat=beat, severity=StakeSeverity.DIRE)
        StakeRewardLineFactory(
            resolution=StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.WIN),
            amount=400,  # within HIGH band (300..1500)
        )
        StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.LOSS)
        # HIGH requires removal reachable within 1 hop: wire a downstream
        # OUTLINE episode whose beat carries a REMOVAL stake.
        fight_episode = EpisodeFactory(chapter=beat.episode.chapter, maturity=StoryMaturity.OUTLINE)
        transition = TransitionFactory(source_episode=beat.episode, target_episode=fight_episode)
        TransitionRequiredOutcome.objects.create(
            transition=transition,
            beat=beat,
            required_outcome=BeatOutcome.FAILURE,
        )
        fight_beat = BeatFactory(episode=fight_episode, risk=RenownRisk.EXTREME)
        StakeFactory(beat=fight_beat, severity=StakeSeverity.REMOVAL)
        return beat

    def test_world_unreviewed_beat_is_not_ready(self) -> None:
        beat = self._ready_world_beat()
        report = validate_stakes_readiness(beat)
        self.assertFalse(report.is_ready)
        self.assertTrue(any("canon" in p.lower() for p in report.problems))

    def test_world_cleared_beat_is_ready(self) -> None:
        beat = self._ready_world_beat()
        review = request_canon_review(beat.episode.chapter.story)
        clear_canon_review(review, AccountFactory())
        report = validate_stakes_readiness(beat)
        self.assertTrue(report.is_ready)
        self.assertFalse(any("canon" in p.lower() for p in report.problems))

    def test_table_tier_beat_has_no_canon_problem(self) -> None:
        story = StoryFactory(impact_tier=ImpactTier.TABLE)
        beat = BeatFactory(
            episode__chapter__story=story,
            risk=RenownRisk.HIGH,
            target_level=4,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
        )
        stake = StakeFactory(beat=beat, severity=StakeSeverity.DIRE)
        StakeRewardLineFactory(
            resolution=StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.WIN),
            amount=400,
        )
        StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.LOSS)
        fight_episode = EpisodeFactory(chapter=beat.episode.chapter, maturity=StoryMaturity.OUTLINE)
        transition = TransitionFactory(source_episode=beat.episode, target_episode=fight_episode)
        TransitionRequiredOutcome.objects.create(
            transition=transition,
            beat=beat,
            required_outcome=BeatOutcome.FAILURE,
        )
        fight_beat = BeatFactory(episode=fight_episode, risk=RenownRisk.EXTREME)
        StakeFactory(beat=fight_beat, severity=StakeSeverity.REMOVAL)
        report = validate_stakes_readiness(beat)
        # TABLE tier is never reviewed — canon-review is not a blocker.
        self.assertTrue(report.is_ready)
        self.assertFalse(any("canon" in p.lower() for p in report.problems))


class EscalationHeuristicTests(TestCase):
    """Beat-level escalation: a GROUP/GLOBAL story with a society-level
    FACTION stake or EXTREME declared risk escalates to >=REGIONAL (#2003).

    Authored data only (never parsed from prose); surfaced as a readiness
    problem, not a hard block. The author's impact_tier is unchanged.
    """

    def test_character_scope_story_never_escalates(self) -> None:
        from world.stories.constants import StoryScope
        from world.stories.services.canon_review import escalation_tier_for_story

        story = StoryFactory(scope=StoryScope.CHARACTER, impact_tier=ImpactTier.TABLE)
        # Even an EXTREME-risk beat does not escalate a CHARACTER-scope story.
        BeatFactory(episode__chapter__story=story, risk=RenownRisk.EXTREME)
        self.assertEqual(escalation_tier_for_story(story), ImpactTier.TABLE)

    def test_group_story_with_extreme_risk_escalates_to_regional(self) -> None:
        from world.stories.constants import StoryScope
        from world.stories.services.canon_review import escalation_tier_for_story

        story = StoryFactory(scope=StoryScope.GROUP, impact_tier=ImpactTier.TABLE)
        BeatFactory(episode__chapter__story=story, risk=RenownRisk.EXTREME)
        self.assertEqual(escalation_tier_for_story(story), ImpactTier.REGIONAL)

    def test_global_story_with_society_faction_stake_escalates_to_regional(self) -> None:
        from world.societies.factories import SocietyFactory
        from world.stories.constants import StakeSubjectKind, StoryScope
        from world.stories.services.canon_review import escalation_tier_for_story

        story = StoryFactory(scope=StoryScope.GLOBAL, impact_tier=ImpactTier.TABLE)
        beat = BeatFactory(episode__chapter__story=story, risk=RenownRisk.HIGH)
        StakeFactory(
            beat=beat,
            subject_kind=StakeSubjectKind.FACTION,
            subject_society=SocietyFactory(),
            severity=StakeSeverity.SETBACK,
        )
        self.assertEqual(escalation_tier_for_story(story), ImpactTier.REGIONAL)

    def test_world_tier_is_not_escalated_further(self) -> None:
        from world.stories.constants import StoryScope
        from world.stories.services.canon_review import escalation_tier_for_story

        story = StoryFactory(scope=StoryScope.GLOBAL, impact_tier=ImpactTier.WORLD)
        BeatFactory(episode__chapter__story=story, risk=RenownRisk.EXTREME)
        # Already WORLD — no further escalation possible.
        self.assertEqual(escalation_tier_for_story(story), ImpactTier.WORLD)

    def test_group_story_without_triggers_stays_at_authored_tier(self) -> None:
        from world.stories.constants import StoryScope
        from world.stories.services.canon_review import escalation_tier_for_story

        story = StoryFactory(scope=StoryScope.GROUP, impact_tier=ImpactTier.TABLE)
        # A HIGH (non-EXTREME) beat with no FACTION stake does not escalate.
        BeatFactory(episode__chapter__story=story, risk=RenownRisk.HIGH)
        self.assertEqual(escalation_tier_for_story(story), ImpactTier.TABLE)

    def test_organization_faction_stake_alone_does_not_escalate(self) -> None:
        """Only society-level FACTION subjects escalate (per spec); an
        org-level FACTION stake alone does not."""
        from world.societies.factories import OrganizationFactory
        from world.stories.constants import StakeSubjectKind, StoryScope
        from world.stories.services.canon_review import escalation_tier_for_story

        story = StoryFactory(scope=StoryScope.GROUP, impact_tier=ImpactTier.TABLE)
        beat = BeatFactory(episode__chapter__story=story, risk=RenownRisk.HIGH)
        StakeFactory(
            beat=beat,
            subject_kind=StakeSubjectKind.FACTION,
            subject_organization=OrganizationFactory(),
            severity=StakeSeverity.SETBACK,
        )
        self.assertEqual(escalation_tier_for_story(story), ImpactTier.TABLE)


class GlobalActivationGateTests(TestCase):
    """GLOBAL-scope WORLD-tier story activation requires a CLEARED review (#2003).

    create_global_progress refuses to activate a WORLD-tier GLOBAL story
    without a cleared canon review (raises StoryError). TABLE/REGIONAL tiers
    and CLEARED WORLD stories activate normally.
    """

    def test_world_global_story_blocked_without_cleared_review(self) -> None:
        from world.stories.constants import StoryScope
        from world.stories.exceptions import StoryError
        from world.stories.services.progress import create_global_progress

        story = StoryFactory(scope=StoryScope.GLOBAL, impact_tier=ImpactTier.WORLD)
        with self.assertRaises(StoryError):
            create_global_progress(story=story)

    def test_world_global_story_activates_after_clear(self) -> None:
        from world.stories.constants import StoryScope
        from world.stories.services.progress import create_global_progress

        story = StoryFactory(scope=StoryScope.GLOBAL, impact_tier=ImpactTier.WORLD)
        review = request_canon_review(story)
        clear_canon_review(review, AccountFactory())
        progress = create_global_progress(story=story)
        self.assertEqual(progress.story, story)

    def test_table_global_story_activates_without_review(self) -> None:
        from world.stories.constants import StoryScope
        from world.stories.services.progress import create_global_progress

        story = StoryFactory(scope=StoryScope.GLOBAL, impact_tier=ImpactTier.TABLE)
        progress = create_global_progress(story=story)
        self.assertEqual(progress.story, story)


class CanonReviewNarrativeNotificationTests(TestCase):
    """clear_canon_review / request_changes fan out a SYSTEM NarrativeMessage
    to the story's owning GMs (#2003).

    The ``_notify_story_owners`` helper mirrors ``custody_clearance._notify_gm``
    (which has its own coverage); here we verify the wiring — that the decision
    services call it with a body naming the story and (for changes) the notes.
    """

    def test_clear_notifies_story_owners(self) -> None:
        from unittest.mock import patch

        from evennia_extensions.factories import AccountFactory

        staff = AccountFactory()
        story = StoryFactory(impact_tier=ImpactTier.WORLD)
        review = request_canon_review(story)
        with patch("world.stories.services.canon_review._notify_story_owners") as mock_notify:
            clear_canon_review(review, staff)
        mock_notify.assert_called_once()
        called_story, kwargs = mock_notify.call_args.args[0], mock_notify.call_args.kwargs
        self.assertEqual(called_story, story)
        self.assertIn(story.title, kwargs["body"])
        self.assertIn("cleared", kwargs["body"].lower())

    def test_changes_notifies_with_notes(self) -> None:
        from unittest.mock import patch

        from evennia_extensions.factories import AccountFactory

        staff = AccountFactory()
        story = StoryFactory(impact_tier=ImpactTier.WORLD)
        review = request_canon_review(story)
        with patch("world.stories.services.canon_review._notify_story_owners") as mock_notify:
            request_changes(review, staff, notes="narrow scope")
        mock_notify.assert_called_once()
        called_story, kwargs = mock_notify.call_args.args[0], mock_notify.call_args.kwargs
        self.assertEqual(called_story, story)
        self.assertIn("narrow scope", kwargs["body"])

    def test_notify_skips_gracefully_when_no_owners(self) -> None:
        """A story with no owning GMs notifies nobody (no error)."""
        from world.narrative.models import NarrativeMessage

        story = StoryFactory(impact_tier=ImpactTier.WORLD)
        # No owners set — _notify_story_owners resolves no GM profiles.
        _notify_story_owners(story, body="test")
        self.assertFalse(NarrativeMessage.objects.filter(related_story=story).exists())


class CanonReviewViewSetTests(APITestCase):
    """Web verbs for the canon-review queue (#2003): list, clear, changes.

    Staff-only; non-staff gets 403. Both lifecycle actions delegate to the
    canon_review service.
    """

    CANON_LIST_URL = "/api/canon-reviews/"

    def _detail_url(self, pk: int) -> str:
        return f"/api/canon-reviews/{pk}/"

    def _clear_url(self, pk: int) -> str:
        return f"/api/canon-reviews/{pk}/clear/"

    def _changes_url(self, pk: int) -> str:
        return f"/api/canon-reviews/{pk}/changes/"

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(is_staff=True)
        cls.non_staff = AccountFactory()
        cls.story = StoryFactory(impact_tier=ImpactTier.WORLD)
        cls.review = request_canon_review(cls.story)

    def test_non_staff_cannot_list(self) -> None:
        self.client.force_authenticate(user=self.non_staff)
        resp = self.client.get(self.CANON_LIST_URL)
        self.assertEqual(resp.status_code, 403)

    def test_staff_can_list_pending(self) -> None:
        self.client.force_authenticate(user=self.staff)
        resp = self.client.get(self.CANON_LIST_URL)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(any(r["id"] == self.review.pk for r in resp.data))

    def test_staff_can_clear_pending_review(self) -> None:
        self.client.force_authenticate(user=self.staff)
        resp = self.client.post(self._clear_url(self.review.pk), {"notes": "ok"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.review.refresh_from_db()
        self.assertEqual(self.review.status, CanonReviewStatus.CLEARED)
        self.assertEqual(self.review.reviewer, self.staff)

    def test_staff_can_request_changes(self) -> None:
        self.client.force_authenticate(user=self.staff)
        resp = self.client.post(
            self._changes_url(self.review.pk), {"notes": "narrow scope"}, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        self.review.refresh_from_db()
        self.assertEqual(self.review.status, CanonReviewStatus.CHANGES_REQUESTED)

    def test_non_staff_cannot_clear(self) -> None:
        self.client.force_authenticate(user=self.non_staff)
        resp = self.client.post(self._clear_url(self.review.pk), {}, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_changes_requires_notes(self) -> None:
        self.client.force_authenticate(user=self.staff)
        resp = self.client.post(self._changes_url(self.review.pk), {}, format="json")
        self.assertEqual(resp.status_code, 400)
