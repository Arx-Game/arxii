"""Tests for Wave 13: atomic save-with-outcomes action on TransitionViewSet.

Covers:
  POST /api/transitions/save-with-outcomes/
    - Happy path: creates Transition + outcomes atomically
    - Happy path update: replaces routing predicates on existing Transition
    - Atomicity: IntegrityError on second outcome rolls back the transition
    - 403 for player (non-GM)
    - 400 validation: target_episode == source_episode
    - No outcomes: creates Transition with empty routing predicates
"""

import json
from unittest.mock import patch

from django.db import IntegrityError
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core_management.test_utils import suppress_permission_errors
from evennia_extensions.factories import AccountFactory
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.stories.constants import BeatOutcome, TransitionMode
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    StoryFactory,
    TransitionFactory,
    TransitionRequiredOutcomeFactory,
)
from world.stories.models import Transition, TransitionRequiredOutcome


class SaveTransitionWithOutcomesViewTest(APITestCase):
    """Tests for POST /api/transitions/save-with-outcomes/."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.lead_gm_account = AccountFactory()
        cls.lead_gm_profile = GMProfileFactory(account=cls.lead_gm_account)
        cls.gm_table = GMTableFactory(gm=cls.lead_gm_profile)
        cls.staff_account = AccountFactory(is_staff=True)
        cls.player_account = AccountFactory()

        cls.story = StoryFactory(
            owners=[cls.lead_gm_account],
            primary_table=cls.gm_table,
        )
        cls.chapter = ChapterFactory(story=cls.story)
        cls.ep1 = EpisodeFactory(chapter=cls.chapter, order=1)
        cls.ep2 = EpisodeFactory(chapter=cls.chapter, order=2)
        cls.ep3 = EpisodeFactory(chapter=cls.chapter, order=3)

        # A beat on ep1 for use in routing predicates.
        cls.beat1 = BeatFactory(episode=cls.ep1)
        cls.beat2 = BeatFactory(episode=cls.ep1)

    @property
    def url(self) -> str:
        return reverse("transition-save-with-outcomes")

    # -----------------------------------------------------------------
    # Create (no existing_id)
    # -----------------------------------------------------------------

    def test_create_transition_and_outcomes_atomically(self) -> None:
        """Lead GM can create a transition with routing predicates in one call."""
        self.client.force_authenticate(user=self.lead_gm_account)
        payload = {
            "source_episode": self.ep1.pk,
            "target_episode": self.ep2.pk,
            "mode": TransitionMode.AUTO,
            "connection_type": "therefore",
            "connection_summary": "Success leads here.",
            "order": 0,
            "outcomes": [
                {"beat": self.beat1.pk, "required_outcome": BeatOutcome.SUCCESS},
            ],
        }
        response = self.client.post(self.url, json.dumps(payload), content_type="application/json")
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["source_episode"] == self.ep1.pk
        assert data["target_episode"] == self.ep2.pk
        # Transition was persisted
        t = Transition.objects.get(pk=data["id"])
        assert t.mode == TransitionMode.AUTO
        # Routing predicates were created
        outcomes = list(t.required_outcomes.all())
        assert len(outcomes) == 1
        assert outcomes[0].beat_id == self.beat1.pk
        assert outcomes[0].required_outcome == BeatOutcome.SUCCESS

    def test_create_transition_no_outcomes(self) -> None:
        """Creating with an empty outcomes list leaves no routing predicates."""
        self.client.force_authenticate(user=self.lead_gm_account)
        payload = {
            "source_episode": self.ep1.pk,
            "target_episode": self.ep3.pk,
            "mode": TransitionMode.GM_CHOICE,
            "outcomes": [],
            "order": 1,
        }
        response = self.client.post(self.url, json.dumps(payload), content_type="application/json")
        assert response.status_code == status.HTTP_201_CREATED
        t = Transition.objects.get(pk=response.json()["id"])
        assert t.required_outcomes.count() == 0

    def test_create_frontier_transition_null_target(self) -> None:
        """Creating with target_episode=null produces a frontier transition."""
        self.client.force_authenticate(user=self.lead_gm_account)
        payload = {
            "source_episode": self.ep1.pk,
            "target_episode": None,
            "mode": TransitionMode.AUTO,
            "outcomes": [],
            "order": 0,
        }
        response = self.client.post(self.url, json.dumps(payload), content_type="application/json")
        assert response.status_code == status.HTTP_201_CREATED
        t = Transition.objects.get(pk=response.json()["id"])
        assert t.target_episode_id is None

    def test_staff_can_create(self) -> None:
        """Staff may create transitions regardless of GM profile."""
        self.client.force_authenticate(user=self.staff_account)
        payload = {
            "source_episode": self.ep1.pk,
            "target_episode": self.ep2.pk,
            "mode": TransitionMode.AUTO,
            "outcomes": [],
            "order": 0,
        }
        response = self.client.post(self.url, json.dumps(payload), content_type="application/json")
        assert response.status_code == status.HTTP_201_CREATED

    # -----------------------------------------------------------------
    # Update (existing_id provided)
    # -----------------------------------------------------------------

    def test_update_transition_replaces_outcomes(self) -> None:
        """Updating with existing_id replaces existing routing predicates."""
        self.client.force_authenticate(user=self.lead_gm_account)
        # Pre-create a transition with one outcome.
        transition = TransitionFactory(
            source_episode=self.ep1,
            target_episode=self.ep2,
            mode=TransitionMode.AUTO,
        )
        TransitionRequiredOutcomeFactory(
            transition=transition,
            beat=self.beat1,
            required_outcome=BeatOutcome.SUCCESS,
        )
        assert transition.required_outcomes.count() == 1

        # Update: change mode and replace routing predicates.
        payload = {
            "existing_id": transition.pk,
            "source_episode": self.ep1.pk,
            "target_episode": self.ep2.pk,
            "mode": TransitionMode.GM_CHOICE,
            "connection_summary": "Updated.",
            "order": 0,
            "outcomes": [
                {"beat": self.beat2.pk, "required_outcome": BeatOutcome.FAILURE},
            ],
        }
        response = self.client.post(self.url, json.dumps(payload), content_type="application/json")
        assert response.status_code == status.HTTP_200_OK
        transition.refresh_from_db()
        assert transition.mode == TransitionMode.GM_CHOICE
        # Old outcome gone, new one present.
        outcomes = list(transition.required_outcomes.all())
        assert len(outcomes) == 1
        assert outcomes[0].beat_id == self.beat2.pk
        assert outcomes[0].required_outcome == BeatOutcome.FAILURE

    def test_update_existing_id_wrong_episode_rejected(self) -> None:
        """existing_id for a different source_episode is rejected."""
        self.client.force_authenticate(user=self.lead_gm_account)
        transition = TransitionFactory(
            source_episode=self.ep2,  # different episode
            target_episode=self.ep3,
        )
        payload = {
            "existing_id": transition.pk,
            "source_episode": self.ep1.pk,  # mismatch
            "target_episode": self.ep2.pk,
            "mode": TransitionMode.AUTO,
            "outcomes": [],
            "order": 0,
        }
        response = self.client.post(self.url, json.dumps(payload), content_type="application/json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    # -----------------------------------------------------------------
    # Atomicity
    # -----------------------------------------------------------------

    def test_rollback_on_integrity_error(self) -> None:
        """If an outcome INSERT fails, the whole transaction rolls back.

        The IntegrityError propagates through the atomic block and DRF
        converts it to a 500 response.  The critical assertion is that no
        Transition was persisted — the atomic() wrapper rolled back the
        partial write.
        """
        self.client.force_authenticate(user=self.lead_gm_account)
        initial_count = Transition.objects.filter(source_episode=self.ep1).count()

        def raise_on_create(*args: object, **kwargs: object) -> "TransitionRequiredOutcome":
            msg = "simulated FK violation"
            raise IntegrityError(msg)

        with patch.object(TransitionRequiredOutcome.objects, "create", side_effect=raise_on_create):
            payload = {
                "source_episode": self.ep1.pk,
                "target_episode": self.ep2.pk,
                "mode": TransitionMode.AUTO,
                "outcomes": [
                    {"beat": self.beat1.pk, "required_outcome": BeatOutcome.SUCCESS},
                ],
                "order": 0,
            }
            response = self.client.post(
                self.url, json.dumps(payload), content_type="application/json"
            )

        # DRF surfaces uncaught exceptions as 500.  The critical invariant is
        # that no Transition was left behind — the atomic() rolled back.
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert Transition.objects.filter(source_episode=self.ep1).count() == initial_count

    # -----------------------------------------------------------------
    # Permission gating
    # -----------------------------------------------------------------

    @suppress_permission_errors
    def test_player_cannot_create(self) -> None:
        """Non-GM player is rejected."""
        self.client.force_authenticate(user=self.player_account)
        payload = {
            "source_episode": self.ep1.pk,
            "target_episode": self.ep2.pk,
            "mode": TransitionMode.AUTO,
            "outcomes": [],
            "order": 0,
        }
        response = self.client.post(self.url, json.dumps(payload), content_type="application/json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_unauthenticated_rejected(self) -> None:
        """Unauthenticated requests are rejected."""
        response = self.client.post(self.url, "{}", content_type="application/json")
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    # -----------------------------------------------------------------
    # Validation
    # -----------------------------------------------------------------

    def test_same_source_and_target_rejected(self) -> None:
        """target_episode == source_episode is a validation error."""
        self.client.force_authenticate(user=self.lead_gm_account)
        payload = {
            "source_episode": self.ep1.pk,
            "target_episode": self.ep1.pk,  # same!
            "mode": TransitionMode.AUTO,
            "outcomes": [],
            "order": 0,
        }
        response = self.client.post(self.url, json.dumps(payload), content_type="application/json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_source_episode_rejected(self) -> None:
        """Missing required source_episode is a validation error."""
        self.client.force_authenticate(user=self.lead_gm_account)
        payload = {
            "mode": TransitionMode.AUTO,
            "outcomes": [],
        }
        response = self.client.post(self.url, json.dumps(payload), content_type="application/json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_multiple_outcomes(self) -> None:
        """Multiple routing predicates are all created."""
        self.client.force_authenticate(user=self.lead_gm_account)
        payload = {
            "source_episode": self.ep1.pk,
            "target_episode": self.ep2.pk,
            "mode": TransitionMode.AUTO,
            "outcomes": [
                {"beat": self.beat1.pk, "required_outcome": BeatOutcome.SUCCESS},
                {"beat": self.beat2.pk, "required_outcome": BeatOutcome.FAILURE},
            ],
            "order": 0,
        }
        response = self.client.post(self.url, json.dumps(payload), content_type="application/json")
        assert response.status_code == status.HTTP_201_CREATED
        t = Transition.objects.get(pk=response.json()["id"])
        assert t.required_outcomes.count() == 2
