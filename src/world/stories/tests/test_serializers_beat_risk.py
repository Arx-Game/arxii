from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.stories.constants import BeatKind, BeatPredicateType
from world.stories.factories import ChapterFactory, EpisodeFactory, StoryFactory


class BeatRiskGateTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.player = AccountFactory(is_staff=False)
        cls.story = StoryFactory(owners=[cls.staff, cls.player])
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter)

    def _payload(self, risk):
        return {
            "episode": self.episode.pk,
            "predicate_type": BeatPredicateType.GM_MARKED,
            "kind": BeatKind.SITUATION,
            "advances": True,
            "risk": risk,
            "internal_description": "x",
        }

    def test_non_staff_cannot_author_risk_above_zero(self):
        self.client.force_authenticate(user=self.player)
        resp = self.client.post(reverse("beat-list"), self._payload(2), format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("risk", resp.data)

    def test_non_staff_may_author_risk_zero(self):
        self.client.force_authenticate(user=self.player)
        resp = self.client.post(reverse("beat-list"), self._payload(0), format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["kind"], BeatKind.SITUATION)

    def test_staff_may_author_any_risk(self):
        self.client.force_authenticate(user=self.staff)
        resp = self.client.post(reverse("beat-list"), self._payload(5), format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["risk"], 5)

    def _create_beat(self, risk):
        """Staff-authored beat at the given risk (staff may author any risk)."""
        self.client.force_authenticate(user=self.staff)
        resp = self.client.post(reverse("beat-list"), self._payload(risk), format="json")
        assert resp.status_code == status.HTTP_201_CREATED, resp.data
        return resp.data["id"]

    def test_non_staff_patch_raising_risk_is_gated(self):
        beat_id = self._create_beat(0)
        self.client.force_authenticate(user=self.player)
        resp = self.client.patch(
            reverse("beat-detail", kwargs={"pk": beat_id}),
            {"risk": 2},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("risk", resp.data)

    def test_non_staff_patch_unrelated_field_on_risk_zero_beat_ok(self):
        # Snapshot-merge carries stored risk=0 through, so the gate does not fire.
        beat_id = self._create_beat(0)
        self.client.force_authenticate(user=self.player)
        resp = self.client.patch(
            reverse("beat-detail", kwargs={"pk": beat_id}),
            {"internal_description": "edited"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_staff_patch_raising_risk_is_allowed(self):
        beat_id = self._create_beat(0)
        self.client.force_authenticate(user=self.staff)
        resp = self.client.patch(
            reverse("beat-detail", kwargs={"pk": beat_id}),
            {"risk": 4},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["risk"], 4)
