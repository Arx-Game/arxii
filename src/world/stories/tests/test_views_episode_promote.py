"""Tests for EpisodeViewSet.promote — Task B1.

Covers POST /api/episodes/{id}/promote/ which exposes the
``promote_episode_maturity`` service via the strict 3-layer pattern.

The PLOT-gate (resting_conclusion + outbound transition / is_ending) is
enforced in PromoteEpisodeInputSerializer.validate(), so a violation returns
400 (not a 500). Demotion / lateral moves are unvalidated by design.
"""

import json

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core_management.test_utils import suppress_permission_errors
from evennia_extensions.factories import AccountFactory
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.stories.constants import StoryMaturity
from world.stories.exceptions import MaturityPromotionError
from world.stories.factories import (
    ChapterFactory,
    EpisodeFactory,
    StoryFactory,
    TransitionFactory,
)


class EpisodePromoteViewSetTest(APITestCase):
    """Tests for POST /api/episodes/{id}/promote/."""

    @classmethod
    def setUpTestData(cls):
        # Story owner / Lead GM (mirrors the resolve / progression-requirement
        # Lead-GM fixture: AccountFactory -> GMProfileFactory -> GMTableFactory
        # -> StoryFactory(owners=[...], primary_table=...)).
        cls.lead_gm_account = AccountFactory()
        cls.lead_gm_profile = GMProfileFactory(account=cls.lead_gm_account)
        cls.gm_table = GMTableFactory(gm=cls.lead_gm_profile)

        cls.staff_account = AccountFactory(is_staff=True)
        cls.unrelated_account = AccountFactory()

        cls.story = StoryFactory(
            owners=[cls.lead_gm_account],
            primary_table=cls.gm_table,
        )
        cls.chapter = ChapterFactory(story=cls.story)

    def _make_episode(self, **kwargs):
        """Create an episode under the Lead-GM story's chapter."""
        return EpisodeFactory(chapter=self.chapter, **kwargs)

    def test_lead_gm_promotes_outline_to_plot_with_transition(self):
        """Lead GM promotes OUTLINE -> PLOT when content requirements are met."""
        episode = self._make_episode(
            maturity=StoryMaturity.OUTLINE,
            resting_conclusion="The dust settles.",
            is_ending=False,
        )
        TransitionFactory(source_episode=episode)

        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("episode-promote", kwargs={"pk": episode.pk})
        response = self.client.post(
            url,
            json.dumps({"target": StoryMaturity.PLOT}),
            content_type="application/json",
        )

        assert response.status_code == status.HTTP_200_OK
        episode.refresh_from_db()
        assert episode.maturity == StoryMaturity.PLOT
        assert response.data["maturity"] == "plot"

    def test_lead_gm_promotes_to_plot_with_is_ending(self):
        """is_ending satisfies the outbound requirement for PLOT."""
        episode = self._make_episode(
            maturity=StoryMaturity.OUTLINE,
            resting_conclusion="The end.",
            is_ending=True,
        )

        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("episode-promote", kwargs={"pk": episode.pk})
        response = self.client.post(
            url,
            json.dumps({"target": StoryMaturity.PLOT}),
            content_type="application/json",
        )

        assert response.status_code == status.HTTP_200_OK
        episode.refresh_from_db()
        assert episode.maturity == StoryMaturity.PLOT
        assert response.data["maturity"] == "plot"

    def test_promote_to_plot_without_resting_conclusion_is_400(self):
        """Empty resting_conclusion blocks promotion to PLOT with a 400."""
        episode = self._make_episode(
            maturity=StoryMaturity.OUTLINE,
            resting_conclusion="",
            is_ending=True,
        )

        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("episode-promote", kwargs={"pk": episode.pk})
        response = self.client.post(
            url,
            json.dumps({"target": StoryMaturity.PLOT}),
            content_type="application/json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert MaturityPromotionError().user_message in json.dumps(response.data)
        episode.refresh_from_db()
        assert episode.maturity == StoryMaturity.OUTLINE

    def test_promote_to_plot_without_transition_or_ending_is_400(self):
        """resting_conclusion set but no outbound transition / ending -> 400."""
        episode = self._make_episode(
            maturity=StoryMaturity.OUTLINE,
            resting_conclusion="It continues somewhere.",
            is_ending=False,
        )

        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("episode-promote", kwargs={"pk": episode.pk})
        response = self.client.post(
            url,
            json.dumps({"target": StoryMaturity.PLOT}),
            content_type="application/json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert MaturityPromotionError().user_message in json.dumps(response.data)
        episode.refresh_from_db()
        assert episode.maturity == StoryMaturity.OUTLINE

    def test_demote_plot_to_outline_is_unvalidated(self):
        """Demotion PLOT -> OUTLINE succeeds with no content requirements."""
        episode = self._make_episode(
            maturity=StoryMaturity.PLOT,
            resting_conclusion="",
            is_ending=False,
        )

        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("episode-promote", kwargs={"pk": episode.pk})
        response = self.client.post(
            url,
            json.dumps({"target": StoryMaturity.OUTLINE}),
            content_type="application/json",
        )

        assert response.status_code == status.HTTP_200_OK
        episode.refresh_from_db()
        assert episode.maturity == StoryMaturity.OUTLINE
        assert response.data["maturity"] == "outline"

    @suppress_permission_errors
    def test_unrelated_user_forbidden(self):
        """A non-owner, non-Lead-GM, non-staff user gets 403."""
        episode = self._make_episode(
            maturity=StoryMaturity.OUTLINE,
            resting_conclusion="Done.",
            is_ending=True,
        )

        self.client.force_authenticate(user=self.unrelated_account)
        url = reverse("episode-promote", kwargs={"pk": episode.pk})
        response = self.client.post(
            url,
            json.dumps({"target": StoryMaturity.PLOT}),
            content_type="application/json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_invalid_target_value_is_400(self):
        """A target not in StoryMaturity is rejected by the ChoiceField."""
        episode = self._make_episode(maturity=StoryMaturity.OUTLINE)

        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("episode-promote", kwargs={"pk": episode.pk})
        response = self.client.post(
            url,
            json.dumps({"target": "not-a-real-maturity"}),
            content_type="application/json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
