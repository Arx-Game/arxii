from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from world.scenes.constants import ScenePrivacyMode
from world.scenes.factories import SceneFactory


class SceneFinishedAfterFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.month_start = timezone.now() - timezone.timedelta(days=30)
        cls.recent = cls.month_start + timezone.timedelta(days=5)
        cls.stale = cls.month_start - timezone.timedelta(days=5)

        # Public, finished inside the window - the only one that should count.
        cls.public_recent = SceneFactory(
            privacy_mode=ScenePrivacyMode.PUBLIC,
            is_active=False,
            date_finished=cls.recent,
        )
        # Public, finished before the window - excluded by finished_after.
        SceneFactory(
            privacy_mode=ScenePrivacyMode.PUBLIC,
            is_active=False,
            date_finished=cls.stale,
        )
        # Private, finished inside the window - excluded by anonymous visibility.
        SceneFactory(
            privacy_mode=ScenePrivacyMode.PRIVATE,
            is_active=False,
            date_finished=cls.recent,
        )

    def test_finished_after_bounds_completed_count(self) -> None:
        client = APIClient()
        resp = client.get(
            reverse("scene-list"),
            {"status": "completed", "finished_after": self.month_start.isoformat()},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 1)  # only the recently finished public scene
