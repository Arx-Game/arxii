"""Task A3: role-gated GM/player visibility split on Story/Chapter/Episode detail.

Security contract: GM-only authoring text (``description``, ``consequences``)
must never leak to a player-tier viewer through the detail API, and a node's
``summary`` must be blanked while that node's maturity is PITCH.

- staff   → full representation (description, consequences, real summary).
- lead_gm → full representation (same as staff).
- player  → no ``description`` / ``consequences`` keys at all; ``summary``
            present but ``""`` for PITCH-maturity nodes, real text otherwise.
"""

from types import SimpleNamespace

from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.stories.constants import StoryMaturity, StoryScope
from world.stories.factories import ChapterFactory, EpisodeFactory, StoryFactory
from world.stories.serializers import (
    ChapterDetailSerializer,
    EpisodeDetailSerializer,
    StoryDetailSerializer,
)

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

    # ------------------------------------------------------------------
    # owner — privileged for their own story's GM text (ledger M-1)
    # ------------------------------------------------------------------

    def test_story_owner_sees_gm_text_on_own_pitch_story(self):
        """A non-staff, non-lead-GM owner of a PITCH story still sees
        ``description`` and a non-blanked ``summary`` on the detail
        endpoint. Without the M-1 fix the owner is classified ``player``
        and the gate strips it (friction reading back their own text)."""
        owner_account = AccountFactory()
        owner_sheet = _make_character_sheet_for_account(owner_account)
        owner_story = StoryFactory(
            scope=StoryScope.CHARACTER,
            character_sheet=owner_sheet,
            primary_table=self.gm_table,
            description=DESCRIPTION_SENTINEL,
            summary=SUMMARY_SENTINEL,
            maturity=StoryMaturity.PITCH,
        )
        owner_story.owners.add(owner_account)
        url = reverse("story-detail", kwargs={"pk": owner_story.pk})

        self.client.force_authenticate(user=owner_account)
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("description", resp.data)
        self.assertEqual(resp.data["description"], DESCRIPTION_SENTINEL)
        self.assertIn("summary", resp.data)
        # PITCH maturity would blank summary for a plain player; owner sees it.
        self.assertEqual(resp.data["summary"], SUMMARY_SENTINEL)


class DefaultDenyVisibilityTests(TestCase):
    """Lock the fail-closed (default-deny) path of ``_gm_text_gate``.

    The most security-critical branch: when there is no request in context
    (``classify_story_log_viewer_role`` never even runs — ``user is None`` →
    ``VIEWER_ROLE_NO_ACCESS``) or the request's user is ``AnonymousUser``
    (``is_authenticated`` is False → ``VIEWER_ROLE_NO_ACCESS``), the Detail
    serializers MUST strip ``description``/``consequences`` and blank a
    PITCH-maturity ``summary``. These tests instantiate the serializers
    directly (not via the API client) so they exercise the gate in isolation
    and pin the default-deny contract against regression.

    A staff sanity test proves the gate is *active*, not vacuous: the same
    serializers, given a staff viewer, must still emit the full representation.
    """

    @classmethod
    def setUpTestData(cls):
        # Mirror StoryDetailVisibilitySplitTests.setUpTestData fixtures so the
        # sentinel text / PITCH-vs-PLOT split is identical.
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

    def _assert_gm_text_stripped(self, story_data, chapter_data, pitch_data, plot_data):
        """Assert the default-deny contract across all four serialized nodes."""
        # Story (PLOT maturity → summary is real text, but no GM text).
        self.assertNotIn("description", story_data)
        self.assertNotIn("consequences", story_data)
        self.assertIn("summary", story_data)
        self.assertEqual(story_data["summary"], SUMMARY_SENTINEL)

        # Chapter (PLOT maturity → summary is real text, no GM text).
        self.assertNotIn("description", chapter_data)
        self.assertNotIn("consequences", chapter_data)
        self.assertIn("summary", chapter_data)
        self.assertEqual(chapter_data["summary"], SUMMARY_SENTINEL)

        # PITCH episode → summary blanked, no GM text.
        self.assertNotIn("description", pitch_data)
        self.assertNotIn("consequences", pitch_data)
        self.assertIn("summary", pitch_data)
        self.assertEqual(pitch_data["summary"], "")

        # PLOT episode → summary is the real sentinel, no GM text.
        self.assertNotIn("description", plot_data)
        self.assertNotIn("consequences", plot_data)
        self.assertIn("summary", plot_data)
        self.assertEqual(plot_data["summary"], SUMMARY_SENTINEL)

    def test_no_request_context_strips_gm_text(self):
        """No request in context → most-restrictive (default-deny) treatment."""
        story_data = StoryDetailSerializer(self.story, context={}).data
        chapter_data = ChapterDetailSerializer(self.chapter, context={}).data
        pitch_data = EpisodeDetailSerializer(self.episode_pitch, context={}).data
        plot_data = EpisodeDetailSerializer(self.episode_plot, context={}).data

        self._assert_gm_text_stripped(story_data, chapter_data, pitch_data, plot_data)

    def test_anonymous_user_strips_gm_text(self):
        """An AnonymousUser request → no_access role → GM text stripped.

        ``_gm_text_gate`` only reads ``request.user``; a SimpleNamespace stub
        is sufficient and avoids constructing a full DRF Request.
        """
        anon_request = SimpleNamespace(user=AnonymousUser())
        ctx = {"request": anon_request}

        story_data = StoryDetailSerializer(self.story, context=ctx).data
        chapter_data = ChapterDetailSerializer(self.chapter, context=ctx).data
        pitch_data = EpisodeDetailSerializer(self.episode_pitch, context=ctx).data
        plot_data = EpisodeDetailSerializer(self.episode_plot, context=ctx).data

        self._assert_gm_text_stripped(story_data, chapter_data, pitch_data, plot_data)

    def test_staff_context_still_full(self):
        """Sanity: staff viewer still gets the full representation.

        Proves the gate is active (not vacuously stripping everything) — the
        same direct-instantiation path, given a staff user, must NOT strip
        ``description``/``consequences`` and must keep the real summary even
        for the PITCH episode. ``classify_story_log_viewer_role`` short-circuits
        on ``is_staff`` before any DB lookup, so a SimpleNamespace stub works.
        """
        staff_request = SimpleNamespace(user=self.staff)
        ctx = {"request": staff_request}

        story_data = StoryDetailSerializer(self.story, context=ctx).data
        self.assertEqual(story_data["description"], DESCRIPTION_SENTINEL)
        self.assertEqual(story_data["summary"], SUMMARY_SENTINEL)

        chapter_data = ChapterDetailSerializer(self.chapter, context=ctx).data
        self.assertEqual(chapter_data["description"], DESCRIPTION_SENTINEL)
        self.assertEqual(chapter_data["consequences"], CONSEQUENCES_SENTINEL)
        self.assertEqual(chapter_data["summary"], SUMMARY_SENTINEL)

        for episode in (self.episode_pitch, self.episode_plot):
            ep_data = EpisodeDetailSerializer(episode, context=ctx).data
            self.assertEqual(ep_data["description"], DESCRIPTION_SENTINEL)
            self.assertEqual(ep_data["consequences"], CONSEQUENCES_SENTINEL)
            self.assertEqual(ep_data["summary"], SUMMARY_SENTINEL)
