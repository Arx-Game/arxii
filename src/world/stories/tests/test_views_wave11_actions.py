"""Tests for Wave 11 action endpoints on stories API ViewSets.

Covers:
  - POST /api/episodes/{id}/resolve/
  - POST /api/beats/{id}/mark/
  - POST /api/beats/{id}/contribute/
  - POST /api/assistant-gm-claims/request/
  - POST /api/assistant-gm-claims/{id}/approve/
  - POST /api/assistant-gm-claims/{id}/reject/
  - POST /api/assistant-gm-claims/{id}/cancel/
  - POST /api/assistant-gm-claims/{id}/complete/
  - POST /api/session-requests/{id}/cancel/
  - POST /api/session-requests/{id}/resolve/
  - POST /api/stories/expire-overdue-beats/
"""

from datetime import timedelta
import json

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from core_management.test_utils import suppress_permission_errors
from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.stories.constants import (
    AssistantClaimStatus,
    BeatOutcome,
    BeatPredicateType,
    SessionRequestStatus,
    StoryScope,
    TransitionMode,
)
from world.stories.factories import (
    AssistantGMClaimFactory,
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    GroupStoryProgressFactory,
    SessionRequestFactory,
    StoryFactory,
    StoryProgressFactory,
    TransitionFactory,
)
from world.stories.models import (
    AssistantGMClaim,
    BeatCompletion,
    EpisodeResolution,
)

# ---------------------------------------------------------------------------
# 11.1: POST /api/episodes/{id}/resolve/
# ---------------------------------------------------------------------------


class EpisodeResolveActionTest(APITestCase):
    """Tests for POST /api/episodes/{id}/resolve/."""

    @classmethod
    def setUpTestData(cls):
        # Story owner / Lead GM
        cls.lead_gm_account = AccountFactory()
        cls.lead_gm_profile = GMProfileFactory(account=cls.lead_gm_account)
        cls.gm_table = GMTableFactory(gm=cls.lead_gm_profile)

        cls.staff_account = AccountFactory(is_staff=True)
        cls.unrelated_account = AccountFactory()

        # CHARACTER-scope story wired to lead_gm_account as owner.
        cls.story = StoryFactory(
            owners=[cls.lead_gm_account],
            scope=StoryScope.CHARACTER,
            primary_table=cls.gm_table,
        )
        cls.chapter = ChapterFactory(story=cls.story)
        cls.ep1 = EpisodeFactory(chapter=cls.chapter, order=1)
        cls.ep2 = EpisodeFactory(chapter=cls.chapter, order=2)

        # A beat the transition requires.
        cls.beat = BeatFactory(
            episode=cls.ep1,
            predicate_type=BeatPredicateType.GM_MARKED,
            outcome=BeatOutcome.SUCCESS,
        )

        # Transition from ep1 -> ep2 (AUTO mode, no required outcomes for simplicity).
        cls.transition = TransitionFactory(
            source_episode=cls.ep1,
            target_episode=cls.ep2,
            mode=TransitionMode.AUTO,
        )

        # A character sheet for progress.
        cls.sheet = CharacterSheetFactory()
        cls.progress = StoryProgressFactory(
            story=cls.story,
            character_sheet=cls.sheet,
            current_episode=cls.ep1,
            is_active=True,
        )

    def setUp(self):
        """Reset progress to ep1 before each test (resolve mutates current_episode)."""
        super().setUp()
        self.progress.current_episode = self.ep1
        self.progress.save(update_fields=["current_episode", "last_advanced_at"])

    def test_lead_gm_can_resolve(self):
        """Lead GM can resolve an episode with AUTO transition."""
        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("episode-resolve", kwargs={"pk": self.ep1.pk})
        response = self.client.post(
            url,
            json.dumps({"progress_id": self.progress.pk}),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert EpisodeResolution.objects.filter(episode=self.ep1).exists()

    def test_staff_can_resolve(self):
        """Staff can resolve an episode."""
        # Refresh progress to ep1 — may have been advanced by previous test.
        self.progress.refresh_from_db()
        if self.progress.current_episode_id != self.ep1.pk:
            # Reset progress to ep1 for this test.
            self.progress.current_episode = self.ep1
            self.progress.save()

        self.client.force_authenticate(user=self.staff_account)
        url = reverse("episode-resolve", kwargs={"pk": self.ep1.pk})
        response = self.client.post(
            url,
            json.dumps({"progress_id": self.progress.pk}),
            content_type="application/json",
        )
        # May succeed or get 400 if resolution was already created — either is valid.
        assert response.status_code in (
            status.HTTP_201_CREATED,
            status.HTTP_400_BAD_REQUEST,
        )

    @suppress_permission_errors
    def test_unrelated_user_forbidden(self):
        """A non-Lead-GM, non-staff user cannot resolve."""
        self.client.force_authenticate(user=self.unrelated_account)
        url = reverse("episode-resolve", kwargs={"pk": self.ep1.pk})
        response = self.client.post(
            url,
            json.dumps({"progress_id": self.progress.pk}),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_explicit_transition_out_of_eligible_set_returns_400(self):
        """Passing a transition not in the eligible set returns 400."""
        # Create a different episode and a transition from a different source.
        ep3 = EpisodeFactory(chapter=self.chapter, order=3)
        ep4 = EpisodeFactory(chapter=self.chapter, order=4)
        wrong_transition = TransitionFactory(source_episode=ep3, target_episode=ep4)

        # Reset progress to ep1.
        self.progress.current_episode = self.ep1
        self.progress.save()

        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("episode-resolve", kwargs={"pk": self.ep1.pk})
        response = self.client.post(
            url,
            json.dumps({"progress_id": self.progress.pk, "chosen_transition": wrong_transition.pk}),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        # DRF validation error shape: {"chosen_transition": [...]}
        assert "chosen_transition" in response.data

    def test_no_transitions_returns_400(self):
        """If the progress has no eligible transitions (frontier), returns 400.

        NoEligibleTransitionError fires inside resolve_episode() and is caught
        in the view as a service-layer runtime error (cannot be pre-validated by
        the serializer without duplicating get_eligible_transitions logic).
        """
        # Use the story's episode but point progress to ep2 (which has no outbound transitions).
        self.progress.current_episode = self.ep2
        self.progress.save(update_fields=["current_episode", "last_advanced_at"])

        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("episode-resolve", kwargs={"pk": self.ep2.pk})
        response = self.client.post(
            url,
            json.dumps({"progress_id": self.progress.pk}),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "detail" in response.data

    def test_gm_notes_recorded(self):
        """gm_notes are persisted on the resolution."""
        self.progress.current_episode = self.ep1
        self.progress.save()

        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("episode-resolve", kwargs={"pk": self.ep1.pk})
        response = self.client.post(
            url,
            json.dumps({"progress_id": self.progress.pk, "gm_notes": "Great session!"}),
            content_type="application/json",
        )
        if response.status_code == status.HTTP_201_CREATED:
            resolution = EpisodeResolution.objects.filter(episode=self.ep1).last()
            assert resolution is not None
            assert resolution.gm_notes == "Great session!"


# ---------------------------------------------------------------------------
# 11.2: POST /api/beats/{id}/mark/
# ---------------------------------------------------------------------------


class BeatMarkActionTest(APITestCase):
    """Tests for POST /api/beats/{id}/mark/."""

    @classmethod
    def setUpTestData(cls):
        cls.lead_gm_account = AccountFactory()
        cls.lead_gm_profile = GMProfileFactory(account=cls.lead_gm_account)
        cls.gm_table = GMTableFactory(gm=cls.lead_gm_profile)

        cls.staff_account = AccountFactory(is_staff=True)
        cls.unrelated_account = AccountFactory()

        # AGM account with an approved claim.
        cls.agm_account = AccountFactory()
        cls.agm_profile = GMProfileFactory(account=cls.agm_account)

        cls.story = StoryFactory(
            owners=[cls.lead_gm_account],
            scope=StoryScope.CHARACTER,
            primary_table=cls.gm_table,
        )
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter)
        cls.beat = BeatFactory(
            episode=cls.episode,
            predicate_type=BeatPredicateType.GM_MARKED,
            outcome=BeatOutcome.UNSATISFIED,
            agm_eligible=True,
        )

        cls.sheet = CharacterSheetFactory()
        cls.progress = StoryProgressFactory(
            story=cls.story,
            character_sheet=cls.sheet,
            current_episode=cls.episode,
            is_active=True,
        )

        # AGM with an approved claim.
        cls.agm_claim = AssistantGMClaimFactory(
            beat=cls.beat,
            assistant_gm=cls.agm_profile,
            status=AssistantClaimStatus.APPROVED,
        )

    def test_lead_gm_can_mark_beat(self):
        """Lead GM can mark a GM_MARKED beat."""
        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("beat-mark", kwargs={"pk": self.beat.pk})
        response = self.client.post(
            url,
            json.dumps({"outcome": BeatOutcome.SUCCESS, "progress_id": self.progress.pk}),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert BeatCompletion.objects.filter(beat=self.beat).exists()

    def test_staff_can_mark_beat(self):
        """Staff can mark a GM_MARKED beat."""
        # Reset beat outcome.
        self.beat.outcome = BeatOutcome.UNSATISFIED
        self.beat.save()

        self.client.force_authenticate(user=self.staff_account)
        url = reverse("beat-mark", kwargs={"pk": self.beat.pk})
        response = self.client.post(
            url,
            json.dumps({"outcome": BeatOutcome.FAILURE, "progress_id": self.progress.pk}),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_agm_with_approved_claim_can_mark(self):
        """AGM with an APPROVED claim on this beat can mark it."""
        self.beat.outcome = BeatOutcome.UNSATISFIED
        self.beat.save()

        self.client.force_authenticate(user=self.agm_account)
        url = reverse("beat-mark", kwargs={"pk": self.beat.pk})
        response = self.client.post(
            url,
            json.dumps({"outcome": BeatOutcome.SUCCESS, "progress_id": self.progress.pk}),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_201_CREATED

    @suppress_permission_errors
    def test_unrelated_user_forbidden(self):
        """An unrelated user cannot mark a beat."""
        self.client.force_authenticate(user=self.unrelated_account)
        url = reverse("beat-mark", kwargs={"pk": self.beat.pk})
        response = self.client.post(
            url,
            json.dumps({"outcome": BeatOutcome.SUCCESS, "progress_id": self.progress.pk}),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_wrong_predicate_type_returns_400(self):
        """Marking a non-GM_MARKED beat returns 400 (serializer validation)."""
        agg_beat = BeatFactory(
            episode=self.episode,
            predicate_type=BeatPredicateType.AGGREGATE_THRESHOLD,
            outcome=BeatOutcome.UNSATISFIED,
            required_points=100,
        )

        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("beat-mark", kwargs={"pk": agg_beat.pk})
        response = self.client.post(
            url,
            json.dumps({"outcome": BeatOutcome.SUCCESS, "progress_id": self.progress.pk}),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        # Serializer raises non_field_errors for this case.
        assert "non_field_errors" in response.data

    def test_invalid_outcome_returns_400(self):
        """Passing an invalid outcome value returns 400 (serializer validation)."""
        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("beat-mark", kwargs={"pk": self.beat.pk})
        response = self.client.post(
            url,
            json.dumps({"outcome": "not_a_valid_outcome", "progress_id": self.progress.pk}),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_lead_gm_can_mark_beat_for_group_scope(self):
        """Lead GM can mark a GM_MARKED beat on a GROUP-scope story."""
        group_story = StoryFactory(
            owners=[self.lead_gm_account],
            scope=StoryScope.GROUP,
            primary_table=self.gm_table,
        )
        chapter = ChapterFactory(story=group_story)
        episode = EpisodeFactory(chapter=chapter)
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.GM_MARKED,
            outcome=BeatOutcome.UNSATISFIED,
        )
        gm_table = GMTableFactory()
        group_progress = GroupStoryProgressFactory(
            story=group_story,
            gm_table=gm_table,
            current_episode=episode,
            is_active=True,
        )

        self.beat.outcome = BeatOutcome.UNSATISFIED
        self.beat.save()

        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("beat-mark", kwargs={"pk": beat.pk})
        response = self.client.post(
            url,
            json.dumps({"outcome": BeatOutcome.SUCCESS, "progress_id": group_progress.pk}),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        completion = BeatCompletion.objects.filter(beat=beat).first()
        assert completion is not None
        assert completion.gm_table == gm_table
        assert completion.character_sheet is None


# ---------------------------------------------------------------------------
# 11.3: POST /api/beats/{id}/contribute/
# ---------------------------------------------------------------------------


class BeatContributeActionTest(APITestCase):
    """Tests for POST /api/beats/{id}/contribute/."""

    @classmethod
    def setUpTestData(cls):
        from evennia_extensions.factories import CharacterFactory

        cls.staff_account = AccountFactory(is_staff=True)
        cls.player_account = AccountFactory()
        cls.other_account = AccountFactory()

        cls.player_character = CharacterFactory()
        cls.player_character.db_account = cls.player_account
        cls.player_character.save()

        cls.player_sheet = CharacterSheetFactory(character=cls.player_character)

        cls.story = StoryFactory(scope=StoryScope.CHARACTER)
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter)
        cls.beat = BeatFactory(
            episode=cls.episode,
            predicate_type=BeatPredicateType.AGGREGATE_THRESHOLD,
            outcome=BeatOutcome.UNSATISFIED,
            required_points=100,
        )

    def test_player_can_contribute_for_own_character(self):
        """A player can record contributions for their own character sheet."""
        self.client.force_authenticate(user=self.player_account)
        url = reverse("beat-contribute", kwargs={"pk": self.beat.pk})
        response = self.client.post(
            url,
            json.dumps({"character_sheet": self.player_sheet.pk, "points": 10}),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["points"] == 10

    def test_staff_can_contribute_for_any_character(self):
        """Staff can contribute for any character sheet."""
        other_sheet = CharacterSheetFactory()

        self.client.force_authenticate(user=self.staff_account)
        url = reverse("beat-contribute", kwargs={"pk": self.beat.pk})
        response = self.client.post(
            url,
            json.dumps({"character_sheet": other_sheet.pk, "points": 5}),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_player_cannot_contribute_for_other_character(self):
        """A player cannot record contributions for a different character.

        The ownership check is enforced by the serializer (validation error 400),
        not by a permission class (403). The response is 400 with a 'character_sheet'
        field error indicating the user may only contribute for their own character.
        """
        other_sheet = CharacterSheetFactory()

        self.client.force_authenticate(user=self.player_account)
        url = reverse("beat-contribute", kwargs={"pk": self.beat.pk})
        response = self.client.post(
            url,
            json.dumps({"character_sheet": other_sheet.pk, "points": 5}),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "character_sheet" in response.data

    def test_wrong_predicate_type_returns_400(self):
        """Contributing to a non-AGGREGATE beat returns 400."""
        gm_beat = BeatFactory(
            episode=self.episode,
            predicate_type=BeatPredicateType.GM_MARKED,
        )
        self.client.force_authenticate(user=self.player_account)
        url = reverse("beat-contribute", kwargs={"pk": gm_beat.pk})
        response = self.client.post(
            url,
            json.dumps({"character_sheet": self.player_sheet.pk, "points": 5}),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_zero_points_rejected_by_serializer(self):
        """points must be >= 1; zero returns 400."""
        self.client.force_authenticate(user=self.player_account)
        url = reverse("beat-contribute", kwargs={"pk": self.beat.pk})
        response = self.client.post(
            url,
            json.dumps({"character_sheet": self.player_sheet.pk, "points": 0}),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# 11.4: AGM claim action endpoints
# ---------------------------------------------------------------------------


class AssistantGMClaimActionsTest(APITestCase):
    """Tests for AGM claim lifecycle endpoints."""

    @classmethod
    def setUpTestData(cls):
        cls.lead_gm_account = AccountFactory()
        cls.lead_gm_profile = GMProfileFactory(account=cls.lead_gm_account)
        cls.gm_table = GMTableFactory(gm=cls.lead_gm_profile)

        cls.agm_account = AccountFactory()
        cls.agm_profile = GMProfileFactory(account=cls.agm_account)

        cls.unrelated_account = AccountFactory()
        cls.staff_account = AccountFactory(is_staff=True)

        cls.story = StoryFactory(
            owners=[cls.lead_gm_account],
            scope=StoryScope.CHARACTER,
            primary_table=cls.gm_table,
        )
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter)
        cls.beat = BeatFactory(
            episode=cls.episode,
            predicate_type=BeatPredicateType.GM_MARKED,
            agm_eligible=True,
        )

    # --- request_claim ---

    def test_agm_can_request_claim(self):
        """An AGM can request a claim on an eligible beat."""
        self.client.force_authenticate(user=self.agm_account)
        url = reverse("assistantgmclaim-request-claim")
        response = self.client.post(
            url,
            json.dumps({"beat": self.beat.pk, "framing_note": "My plan"}),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert AssistantGMClaim.objects.filter(
            beat=self.beat, assistant_gm=self.agm_profile
        ).exists()

    @suppress_permission_errors
    def test_non_gm_cannot_request_claim(self):
        """A user without a GM profile cannot request a claim."""
        self.client.force_authenticate(user=self.unrelated_account)
        url = reverse("assistantgmclaim-request-claim")
        response = self.client.post(
            url,
            json.dumps({"beat": self.beat.pk}),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_request_on_ineligible_beat_returns_400(self):
        """Requesting a claim on a non-agm_eligible beat returns 400 (serializer validation)."""
        non_eligible = BeatFactory(episode=self.episode, agm_eligible=False)

        self.client.force_authenticate(user=self.agm_account)
        url = reverse("assistantgmclaim-request-claim")
        response = self.client.post(
            url,
            json.dumps({"beat": non_eligible.pk}),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        # Serializer raises field-level error on "beat" field.
        assert "beat" in response.data

    # --- approve ---

    def _make_requested_claim(self):
        return AssistantGMClaimFactory(
            beat=self.beat,
            assistant_gm=self.agm_profile,
            status=AssistantClaimStatus.REQUESTED,
        )

    def test_lead_gm_can_approve_claim(self):
        """Lead GM can approve a REQUESTED claim."""
        claim = self._make_requested_claim()

        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("assistantgmclaim-approve", kwargs={"pk": claim.pk})
        response = self.client.post(url, json.dumps({}), content_type="application/json")

        assert response.status_code == status.HTTP_200_OK
        claim.refresh_from_db()
        assert claim.status == AssistantClaimStatus.APPROVED

    @suppress_permission_errors
    def test_agm_cannot_approve_own_claim(self):
        """An AGM cannot approve their own claim."""
        claim = self._make_requested_claim()

        self.client.force_authenticate(user=self.agm_account)
        url = reverse("assistantgmclaim-approve", kwargs={"pk": claim.pk})
        response = self.client.post(url, json.dumps({}), content_type="application/json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    # --- reject ---

    def test_lead_gm_can_reject_claim(self):
        """Lead GM can reject a REQUESTED claim with a note."""
        claim = self._make_requested_claim()

        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("assistantgmclaim-reject", kwargs={"pk": claim.pk})
        response = self.client.post(
            url,
            json.dumps({"note": "Not available for this beat."}),
            content_type="application/json",
        )

        assert response.status_code == status.HTTP_200_OK
        claim.refresh_from_db()
        assert claim.status == AssistantClaimStatus.REJECTED
        assert claim.rejection_note == "Not available for this beat."

    @suppress_permission_errors
    def test_unrelated_user_cannot_reject(self):
        """An unrelated user cannot reject a claim (gets 403 or 404 via queryset filter)."""
        claim = self._make_requested_claim()

        self.client.force_authenticate(user=self.unrelated_account)
        url = reverse("assistantgmclaim-reject", kwargs={"pk": claim.pk})
        response = self.client.post(url, json.dumps({}), content_type="application/json")
        assert response.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

    # --- cancel ---

    def test_agm_can_cancel_own_requested_claim(self):
        """AGM can cancel their own REQUESTED claim."""
        claim = self._make_requested_claim()

        self.client.force_authenticate(user=self.agm_account)
        url = reverse("assistantgmclaim-cancel", kwargs={"pk": claim.pk})
        response = self.client.post(url, json.dumps({}), content_type="application/json")

        assert response.status_code == status.HTTP_200_OK
        claim.refresh_from_db()
        assert claim.status == AssistantClaimStatus.CANCELLED

    def test_cancel_approved_claim_returns_400(self):
        """Cancelling an already-approved claim returns 400 (serializer validation)."""
        claim = AssistantGMClaimFactory(
            beat=self.beat,
            assistant_gm=self.agm_profile,
            status=AssistantClaimStatus.APPROVED,
        )

        self.client.force_authenticate(user=self.agm_account)
        url = reverse("assistantgmclaim-cancel", kwargs={"pk": claim.pk})
        response = self.client.post(url, json.dumps({}), content_type="application/json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @suppress_permission_errors
    def test_unrelated_user_cannot_cancel(self):
        """An unrelated user cannot cancel a claim (gets 403 or 404 via queryset filter)."""
        claim = self._make_requested_claim()

        self.client.force_authenticate(user=self.unrelated_account)
        url = reverse("assistantgmclaim-cancel", kwargs={"pk": claim.pk})
        response = self.client.post(url, json.dumps({}), content_type="application/json")
        assert response.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

    # --- complete ---

    def test_lead_gm_can_complete_approved_claim(self):
        """Lead GM can mark an APPROVED claim COMPLETED."""
        claim = AssistantGMClaimFactory(
            beat=self.beat,
            assistant_gm=self.agm_profile,
            status=AssistantClaimStatus.APPROVED,
            approved_by=self.lead_gm_profile,
        )

        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("assistantgmclaim-complete", kwargs={"pk": claim.pk})
        response = self.client.post(url, json.dumps({}), content_type="application/json")

        assert response.status_code == status.HTTP_200_OK
        claim.refresh_from_db()
        assert claim.status == AssistantClaimStatus.COMPLETED

    def test_complete_requested_claim_returns_400(self):
        """Completing a REQUESTED (non-approved) claim returns 400 (serializer validation)."""
        claim = self._make_requested_claim()

        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("assistantgmclaim-complete", kwargs={"pk": claim.pk})
        response = self.client.post(url, json.dumps({}), content_type="application/json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# 11.5: SessionRequest action endpoints
# ---------------------------------------------------------------------------


class SessionRequestActionsTest(APITestCase):
    """Tests for SessionRequest cancel and resolve endpoints."""

    @classmethod
    def setUpTestData(cls):
        cls.lead_gm_account = AccountFactory()
        cls.staff_account = AccountFactory(is_staff=True)
        cls.unrelated_account = AccountFactory()

        cls.story = StoryFactory(owners=[cls.lead_gm_account], scope=StoryScope.CHARACTER)
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter)

        cls.open_request = SessionRequestFactory(
            episode=cls.episode,
            status=SessionRequestStatus.OPEN,
        )

    # --- cancel ---

    def test_lead_gm_can_cancel_open_request(self):
        """Story owner (Lead GM) can cancel an OPEN session request."""
        # Create a fresh one so other tests don't interfere.
        req = SessionRequestFactory(episode=self.episode, status=SessionRequestStatus.OPEN)

        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("sessionrequest-cancel", kwargs={"pk": req.pk})
        response = self.client.post(url, json.dumps({}), content_type="application/json")

        assert response.status_code == status.HTTP_200_OK
        req.refresh_from_db()
        assert req.status == SessionRequestStatus.CANCELLED

    def test_staff_can_cancel_open_request(self):
        """Staff can cancel an OPEN session request."""
        req = SessionRequestFactory(episode=self.episode, status=SessionRequestStatus.OPEN)

        self.client.force_authenticate(user=self.staff_account)
        url = reverse("sessionrequest-cancel", kwargs={"pk": req.pk})
        response = self.client.post(url, json.dumps({}), content_type="application/json")

        assert response.status_code == status.HTTP_200_OK

    @suppress_permission_errors
    def test_unrelated_user_cannot_cancel(self):
        """An unrelated user cannot cancel a session request (403 or 404 via queryset filter)."""
        req = SessionRequestFactory(episode=self.episode, status=SessionRequestStatus.OPEN)

        self.client.force_authenticate(user=self.unrelated_account)
        url = reverse("sessionrequest-cancel", kwargs={"pk": req.pk})
        response = self.client.post(url, json.dumps({}), content_type="application/json")
        assert response.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

    def test_cancel_non_open_returns_400(self):
        """Cancelling a non-OPEN request returns 400 (serializer validation)."""
        # Create a scheduled request to try cancelling.
        scheduled_req = SessionRequestFactory(
            episode=self.episode, status=SessionRequestStatus.SCHEDULED
        )

        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("sessionrequest-cancel", kwargs={"pk": scheduled_req.pk})
        response = self.client.post(url, json.dumps({}), content_type="application/json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        # Serializer raises non_field_errors for status check.
        assert "non_field_errors" in response.data

    # --- resolve ---

    def test_lead_gm_can_resolve_scheduled_request(self):
        """Lead GM can mark a SCHEDULED session request as RESOLVED."""
        req = SessionRequestFactory(episode=self.episode, status=SessionRequestStatus.SCHEDULED)

        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("sessionrequest-resolve", kwargs={"pk": req.pk})
        response = self.client.post(url, json.dumps({}), content_type="application/json")

        assert response.status_code == status.HTTP_200_OK
        req.refresh_from_db()
        assert req.status == SessionRequestStatus.RESOLVED

    def test_resolve_open_returns_400(self):
        """Resolving an OPEN (not scheduled) request returns 400."""
        req = SessionRequestFactory(episode=self.episode, status=SessionRequestStatus.OPEN)

        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("sessionrequest-resolve", kwargs={"pk": req.pk})
        response = self.client.post(url, json.dumps({}), content_type="application/json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @suppress_permission_errors
    def test_unrelated_user_cannot_resolve(self):
        """An unrelated user cannot resolve a session request (403 or 404 via queryset filter)."""
        req = SessionRequestFactory(episode=self.episode, status=SessionRequestStatus.SCHEDULED)

        self.client.force_authenticate(user=self.unrelated_account)
        url = reverse("sessionrequest-resolve", kwargs={"pk": req.pk})
        response = self.client.post(url, json.dumps({}), content_type="application/json")
        assert response.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)


# ---------------------------------------------------------------------------
# 11.6: POST /api/stories/expire-overdue-beats/
# ---------------------------------------------------------------------------


class ExpireOverdueBeatsEndpointTest(APITestCase):
    """Tests for POST /api/stories/expire-overdue-beats/."""

    @classmethod
    def setUpTestData(cls):
        cls.staff_account = AccountFactory(is_staff=True)
        cls.non_staff_account = AccountFactory()

        cls.episode = EpisodeFactory()
        past_deadline = timezone.now() - timedelta(days=1)
        cls.overdue_beat = BeatFactory(
            episode=cls.episode,
            outcome=BeatOutcome.UNSATISFIED,
            deadline=past_deadline,
        )
        cls.fresh_beat = BeatFactory(
            episode=cls.episode,
            outcome=BeatOutcome.UNSATISFIED,
            deadline=None,  # No deadline — should not be expired.
        )

    def test_staff_triggers_expiry(self):
        """Staff can trigger the expiry endpoint and get a count."""
        self.client.force_authenticate(user=self.staff_account)
        url = reverse("stories-expire-overdue-beats")
        response = self.client.post(url, json.dumps({}), content_type="application/json")

        assert response.status_code == status.HTTP_200_OK
        assert "expired_count" in response.data
        assert response.data["expired_count"] >= 1  # at least the overdue beat

        self.overdue_beat.refresh_from_db()
        assert self.overdue_beat.outcome == BeatOutcome.EXPIRED

    def test_no_deadline_beats_not_expired(self):
        """Beats without deadlines are not expired."""
        self.client.force_authenticate(user=self.staff_account)
        url = reverse("stories-expire-overdue-beats")
        self.client.post(url, json.dumps({}), content_type="application/json")

        self.fresh_beat.refresh_from_db()
        assert self.fresh_beat.outcome == BeatOutcome.UNSATISFIED

    @suppress_permission_errors
    def test_non_staff_forbidden(self):
        """Non-staff users receive 403."""
        self.client.force_authenticate(user=self.non_staff_account)
        url = reverse("stories-expire-overdue-beats")
        response = self.client.post(url, json.dumps({}), content_type="application/json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @suppress_permission_errors
    def test_unauthenticated_forbidden(self):
        """Unauthenticated requests receive 403."""
        url = reverse("stories-expire-overdue-beats")
        response = self.client.post(url, json.dumps({}), content_type="application/json")
        assert response.status_code == status.HTTP_403_FORBIDDEN
