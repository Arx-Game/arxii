from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.stories.factories import ChapterFactory, EpisodeFactory, StoryFactory


class AuthoringFieldExposureTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.story = StoryFactory(owners=[cls.staff])
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter)

    def setUp(self):
        self.client.force_authenticate(user=self.staff)

    def test_story_detail_exposes_summary_and_maturity(self):
        resp = self.client.get(reverse("story-detail", kwargs={"pk": self.story.pk}))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("summary", resp.data)
        self.assertIn("maturity", resp.data)

    def test_story_summary_is_writable(self):
        url = reverse("story-detail", kwargs={"pk": self.story.pk})
        resp = self.client.patch(url, {"summary": "recap text"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        re_get = self.client.get(url)
        self.assertEqual(re_get.status_code, status.HTTP_200_OK)
        self.assertEqual(re_get.data["summary"], "recap text")

    def test_chapter_detail_exposes_maturity(self):
        resp = self.client.get(reverse("chapter-detail", kwargs={"pk": self.chapter.pk}))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("maturity", resp.data)

    def test_episode_detail_exposes_authoring_fields(self):
        resp = self.client.get(reverse("episode-detail", kwargs={"pk": self.episode.pk}))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("maturity", resp.data)
        self.assertIn("resting_conclusion", resp.data)
        self.assertIn("is_ending", resp.data)

    def test_episode_authoring_fields_are_writable(self):
        url = reverse("episode-detail", kwargs={"pk": self.episode.pk})
        resp = self.client.patch(
            url,
            {"is_ending": True, "resting_conclusion": "ends"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        re_get = self.client.get(url)
        self.assertEqual(re_get.status_code, status.HTTP_200_OK)
        self.assertTrue(re_get.data["is_ending"])
        self.assertEqual(re_get.data["resting_conclusion"], "ends")
