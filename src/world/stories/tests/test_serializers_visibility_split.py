"""Task A3: role-gated GM/player visibility split on Story/Chapter/Episode detail.

Security contract: GM-only authoring text (``description``, ``consequences``)
must never leak to a player-tier viewer through the detail API, and a node's
``summary`` must be blanked while that node's maturity is PITCH.

- staff   → full representation (description, consequences, real summary).
- lead_gm → full representation (same as staff).
- player  → no ``description`` / ``consequences`` keys at all; ``summary``
            present but ``""`` for PITCH-maturity nodes, real text otherwise.
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.stories.constants import StoryMaturity, StoryScope
from world.stories.factories import ChapterFactory, EpisodeFactory, StoryFactory

DESCRIPTION_SENTINEL = "GM-only authoring description sentinel"
CONSEQUENCES_SENTINEL = "GM-only consequences sentinel"
SUMMARY_SENTINEL = "Player-facing recap sentinel"


def _make_character_sheet_for_account(account):
    """Create a CharacterSheet whose ObjectDB character is owned by account."""
    char = CharacterFactory()
    char.db_account = account
    char.save()
    return CharacterSheetFactory(character=char)


class StoryDetailVisibilitySplitTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)

        cls.lead_gm_account = AccountFactory()
        cls.lead_gm_profile = GMProfileFactory(account=cls.lead_gm_account)
        cls.gm_table = GMTableFactory(gm=cls.lead_gm_profile)

        cls.player_account = AccountFactory()
        cls.player_sheet = _make_character_sheet_for_account(cls.player_account)

        cls.story = StoryFactory(
            scope=StoryScope.CHARACTER,
            character_sheet=cls.player_sheet,
            primary_table=cls.gm_table,
            description=DESCRIPTION_SENTINEL,
            summary=SUMMARY_SENTINEL,
            maturity=StoryMaturity.PLOT,
        )
        cls.chapter = ChapterFactory(
            story=cls.story,
            description=DESCRIPTION_SENTINEL,
            summary=SUMMARY_SENTINEL,
            consequences=CONSEQUENCES_SENTINEL,
            maturity=StoryMaturity.PLOT,
        )
        cls.episode_pitch = EpisodeFactory(
            chapter=cls.chapter,
            order=1,
            description=DESCRIPTION_SENTINEL,
            summary=SUMMARY_SENTINEL,
            consequences=CONSEQUENCES_SENTINEL,
            maturity=StoryMaturity.PITCH,
        )
        cls.episode_plot = EpisodeFactory(
            chapter=cls.chapter,
            order=2,
            description=DESCRIPTION_SENTINEL,
            summary=SUMMARY_SENTINEL,
            consequences=CONSEQUENCES_SENTINEL,
            maturity=StoryMaturity.PLOT,
        )

        cls.story_url = reverse("story-detail", kwargs={"pk": cls.story.pk})
        cls.chapter_url = reverse("chapter-detail", kwargs={"pk": cls.chapter.pk})
        cls.ep_pitch_url = reverse("episode-detail", kwargs={"pk": cls.episode_pitch.pk})
        cls.ep_plot_url = reverse("episode-detail", kwargs={"pk": cls.episode_plot.pk})

    # ------------------------------------------------------------------
    # staff — full representation
    # ------------------------------------------------------------------

    def test_staff_sees_full_representation(self):
        self.client.force_authenticate(user=self.staff)

        story = self.client.get(self.story_url)
        self.assertEqual(story.status_code, status.HTTP_200_OK)
        self.assertEqual(story.data["description"], DESCRIPTION_SENTINEL)
        self.assertEqual(story.data["summary"], SUMMARY_SENTINEL)

        chapter = self.client.get(self.chapter_url)
        self.assertEqual(chapter.status_code, status.HTTP_200_OK)
        self.assertEqual(chapter.data["description"], DESCRIPTION_SENTINEL)
        self.assertEqual(chapter.data["consequences"], CONSEQUENCES_SENTINEL)
        self.assertEqual(chapter.data["summary"], SUMMARY_SENTINEL)

        for url in (self.ep_pitch_url, self.ep_plot_url):
            ep = self.client.get(url)
            self.assertEqual(ep.status_code, status.HTTP_200_OK)
            self.assertEqual(ep.data["description"], DESCRIPTION_SENTINEL)
            self.assertEqual(ep.data["consequences"], CONSEQUENCES_SENTINEL)
            self.assertEqual(ep.data["summary"], SUMMARY_SENTINEL)

    # ------------------------------------------------------------------
    # lead_gm — full representation (same as staff)
    # ------------------------------------------------------------------

    def test_lead_gm_sees_full_representation(self):
        self.client.force_authenticate(user=self.lead_gm_account)

        story = self.client.get(self.story_url)
        self.assertEqual(story.status_code, status.HTTP_200_OK)
        self.assertEqual(story.data["description"], DESCRIPTION_SENTINEL)
        self.assertEqual(story.data["summary"], SUMMARY_SENTINEL)

        chapter = self.client.get(self.chapter_url)
        self.assertEqual(chapter.status_code, status.HTTP_200_OK)
        self.assertEqual(chapter.data["description"], DESCRIPTION_SENTINEL)
        self.assertEqual(chapter.data["consequences"], CONSEQUENCES_SENTINEL)
        self.assertEqual(chapter.data["summary"], SUMMARY_SENTINEL)

        for url in (self.ep_pitch_url, self.ep_plot_url):
            ep = self.client.get(url)
            self.assertEqual(ep.status_code, status.HTTP_200_OK)
            self.assertEqual(ep.data["description"], DESCRIPTION_SENTINEL)
            self.assertEqual(ep.data["consequences"], CONSEQUENCES_SENTINEL)
            self.assertEqual(ep.data["summary"], SUMMARY_SENTINEL)

    # ------------------------------------------------------------------
    # player — GM text suppressed, PITCH summary blanked
    # ------------------------------------------------------------------

    def test_player_story_has_no_description_summary_present(self):
        self.client.force_authenticate(user=self.player_account)
        resp = self.client.get(self.story_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertNotIn("description", resp.data)
        self.assertNotIn("consequences", resp.data)
        self.assertIn("summary", resp.data)
        # Story maturity is PLOT → summary is real text.
        self.assertEqual(resp.data["summary"], SUMMARY_SENTINEL)

    def test_player_chapter_has_no_gm_text(self):
        self.client.force_authenticate(user=self.player_account)
        resp = self.client.get(self.chapter_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertNotIn("description", resp.data)
        self.assertNotIn("consequences", resp.data)
        self.assertIn("summary", resp.data)
        # Chapter maturity is PLOT → summary is real text.
        self.assertEqual(resp.data["summary"], SUMMARY_SENTINEL)

    def test_player_pitch_episode_summary_blanked(self):
        self.client.force_authenticate(user=self.player_account)
        resp = self.client.get(self.ep_pitch_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertNotIn("description", resp.data)
        self.assertNotIn("consequences", resp.data)
        self.assertIn("summary", resp.data)
        self.assertEqual(resp.data["summary"], "")

    def test_player_plot_episode_summary_present(self):
        self.client.force_authenticate(user=self.player_account)
        resp = self.client.get(self.ep_plot_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertNotIn("description", resp.data)
        self.assertNotIn("consequences", resp.data)
        self.assertIn("summary", resp.data)
        self.assertEqual(resp.data["summary"], SUMMARY_SENTINEL)
