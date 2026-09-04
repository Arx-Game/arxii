"""GET /api/beats/{id}/readiness/ - GM readiness dashboard for a beat (#3562).

Unlike stakes-summary (player-safe, pillar 9), readiness surfaces the raw
``problems`` list - GM planning detail like ``internal_description`` - so
it is gated to the Lead GM or staff via ``CanAssignMissionToBeat``, not
opened to any story participant.
"""

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.societies.constants import RenownRisk
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    StoryFactory,
)
from world.stories.models import StakeContractActivation


class BeatReadinessEndpointTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.story = StoryFactory()
        self.chapter = ChapterFactory(story=self.story)
        self.episode = EpisodeFactory(chapter=self.chapter)
        # Risky and lacking target_level -> unready with non-empty problems.
        self.beat = BeatFactory(episode=self.episode, risk=RenownRisk.MODERATE, target_level=0)

    def _url(self):
        return reverse("beat-readiness", kwargs={"pk": self.beat.pk})

    def _make_lead_gm(self):
        gm_account = AccountFactory(is_staff=False)
        gm_profile = GMProfileFactory(account=gm_account)
        table = GMTableFactory(gm=gm_profile)
        self.story.primary_table = table
        self.story.save()
        return gm_account

    def test_lead_gm_sees_problems_on_unready_beat(self) -> None:
        gm_account = self._make_lead_gm()
        self.client.force_authenticate(user=gm_account)
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        self.assertTrue(resp.data["is_staked"])
        self.assertFalse(resp.data["is_ready"])
        self.assertTrue(resp.data["problems"])
        self.assertEqual(resp.data["declared_risk"], RenownRisk.MODERATE)
        self.assertEqual(resp.data["effective_risk"], RenownRisk.MODERATE)
        self.assertFalse(resp.data["locked"])
        self.assertIsNone(resp.data["locked_at"])

    def test_player_forbidden(self) -> None:
        account = AccountFactory(is_staff=False)
        self.client.force_authenticate(user=account)
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN, resp.content)

    def test_staff_allowed(self) -> None:
        staff = AccountFactory(is_staff=True)
        self.client.force_authenticate(user=staff)
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)

    def test_open_activation_reports_locked(self) -> None:
        StakeContractActivation.objects.create(
            beat=self.beat,
            party_average_level=5,
            declared_target_level=0,
            declared_risk=self.beat.risk,
            effective_risk=RenownRisk.NONE,
            is_ready=False,
        )
        staff = AccountFactory(is_staff=True)
        self.client.force_authenticate(user=staff)
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        self.assertTrue(resp.data["locked"])
        self.assertIsNotNone(resp.data["locked_at"])
        self.assertEqual(resp.data["effective_risk"], RenownRisk.NONE)
