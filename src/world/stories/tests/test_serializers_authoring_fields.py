from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.stories.factories import ChapterFactory, EpisodeFactory, StoryFactory
from world.stories.models import Chapter, Episode, Story


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

    # ------------------------------------------------------------------
    # I-B: create serializers must honor authoring inputs (no silent drop)
    # ------------------------------------------------------------------

    def test_episode_create_persists_summary_resting_conclusion_is_ending(self):
        """POST /api/episodes/ must persist authoring fields the E2 form submits.

        Before the EpisodeCreateSerializer fix these undeclared keys were
        silently dropped by DRF (the create succeeded but the data was lost).
        """
        resp = self.client.post(
            reverse("episode-list"),
            {
                "chapter": self.chapter.pk,
                "title": "Created Episode",
                "description": "GM desc",
                "order": 99,
                "summary": "the story so far",
                "resting_conclusion": "it rests here",
                "is_ending": True,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        created = Episode.objects.get(title="Created Episode")
        re_get = self.client.get(reverse("episode-detail", kwargs={"pk": created.pk}))
        self.assertEqual(re_get.status_code, status.HTTP_200_OK)
        self.assertEqual(re_get.data["summary"], "the story so far")
        self.assertEqual(re_get.data["resting_conclusion"], "it rests here")
        self.assertTrue(re_get.data["is_ending"])

    def test_chapter_create_persists_summary(self):
        """POST /api/chapters/ must persist the summary the E2 form submits."""
        resp = self.client.post(
            reverse("chapter-list"),
            {
                "story": self.story.pk,
                "title": "Created Chapter",
                "description": "GM desc",
                "order": 99,
                "summary": "chapter recap text",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        created = Chapter.objects.get(title="Created Chapter")
        re_get = self.client.get(reverse("chapter-detail", kwargs={"pk": created.pk}))
        self.assertEqual(re_get.status_code, status.HTTP_200_OK)
        self.assertEqual(re_get.data["summary"], "chapter recap text")

    def test_story_create_persists_summary(self):
        """POST /api/stories/ persists summary (A2 already exposes it; guard)."""
        resp = self.client.post(
            reverse("story-list"),
            {
                "title": "Created Story",
                "description": "GM desc",
                "summary": "story recap text",
                "privacy": "private",
                "scope": "unassigned",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        created = Story.objects.get(title="Created Story")
        re_get = self.client.get(reverse("story-detail", kwargs={"pk": created.pk}))
        self.assertEqual(re_get.status_code, status.HTTP_200_OK)
        self.assertEqual(re_get.data["summary"], "story recap text")
