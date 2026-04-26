"""Tests for GET /api/stories/{id}/log/ action on StoryViewSet.

Covers all four viewer-role tiers:
- staff: sees all fields (internal_description, gm_notes)
- lead_gm: sees all fields
- player (story character owner): sees player-facing text; no internal fields
- no_access: 403
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.stories.constants import BeatOutcome, BeatVisibility, StoryScope
from world.stories.factories import (
    BeatCompletionFactory,
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    EpisodeResolutionFactory,
    StoryFactory,
    StoryProgressFactory,
    TransitionFactory,
)


def _make_character_sheet_for_account(account):
    """Create a CharacterSheet whose ObjectDB character is owned by account."""
    char = CharacterFactory()
    char.db_account = account
    char.save()
    return CharacterSheetFactory(character=char)


class StoryLogActionTests(APITestCase):
    """Tests for GET /api/stories/{id}/log/."""

    @classmethod
    def setUpTestData(cls):
        # Staff account
        cls.staff_account = AccountFactory(is_staff=True)

        # Lead GM: GMProfile + GMTable linked as story's primary_table
        cls.lead_gm_account = AccountFactory()
        cls.lead_gm_profile = GMProfileFactory(account=cls.lead_gm_account)
        cls.gm_table = GMTableFactory(gm=cls.lead_gm_profile)

        # Player: account whose character owns the story
        cls.player_account = AccountFactory()
        cls.player_sheet = _make_character_sheet_for_account(cls.player_account)

        # Unrelated account — no access
        cls.outsider_account = AccountFactory()

        # CHARACTER-scope story owned by the player's character
        cls.story = StoryFactory(
            scope=StoryScope.CHARACTER,
            character_sheet=cls.player_sheet,
            primary_table=cls.gm_table,
        )
        cls.chapter = ChapterFactory(story=cls.story, order=1)
        cls.ep1 = EpisodeFactory(chapter=cls.chapter, order=1)
        cls.ep2 = EpisodeFactory(chapter=cls.chapter, order=2)

        # Transition so EpisodeResolution can reference one
        cls.transition = TransitionFactory(
            source_episode=cls.ep1,
            target_episode=cls.ep2,
        )

        # One HINTED beat and one SECRET beat
        cls.hinted_beat = BeatFactory(
            episode=cls.ep1,
            visibility=BeatVisibility.HINTED,
            player_hint="A clue for the player",
            player_resolution_text="It was resolved",
            internal_description="GM-only context",
        )
        cls.secret_beat = BeatFactory(
            episode=cls.ep1,
            visibility=BeatVisibility.SECRET,
            player_hint="Secret hint",
            player_resolution_text="Secret resolution",
            internal_description="Secret GM context",
        )

        # Active progress for the player's sheet
        cls.progress = StoryProgressFactory(
            story=cls.story,
            character_sheet=cls.player_sheet,
            current_episode=cls.ep1,
            is_active=True,
        )

        # Completions for both beats, attached to the player's sheet
        cls.hinted_completion = BeatCompletionFactory(
            beat=cls.hinted_beat,
            character_sheet=cls.player_sheet,
            outcome=BeatOutcome.SUCCESS,
            gm_notes="GM only note",
        )
        cls.secret_completion = BeatCompletionFactory(
            beat=cls.secret_beat,
            character_sheet=cls.player_sheet,
            outcome=BeatOutcome.SUCCESS,
            gm_notes="Secret GM note",
        )

        # One episode resolution
        cls.resolution = EpisodeResolutionFactory(
            episode=cls.ep1,
            character_sheet=cls.player_sheet,
            chosen_transition=cls.transition,
            gm_notes="Resolution GM note",
        )

    # -------------------------------------------------------------------------
    # Helper
    # -------------------------------------------------------------------------

    def _log_url(self):
        return reverse("story-log", kwargs={"pk": self.story.pk})

    # -------------------------------------------------------------------------
    # 200 path: staff sees everything
    # -------------------------------------------------------------------------

    def test_staff_sees_full_log(self):
        """Staff receives 200 with internal fields present."""
        self.client.force_authenticate(user=self.staff_account)
        response = self.client.get(self._log_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        entries = response.data["entries"]
        self.assertGreater(len(entries), 0)

        beat_entries = [e for e in entries if e["entry_type"] == "beat_completion"]
        self.assertGreater(len(beat_entries), 0)

        # Staff sees internal_description and gm_notes
        hinted_entry = next(e for e in beat_entries if e["beat_id"] == self.hinted_beat.pk)
        self.assertEqual(hinted_entry["internal_description"], "GM-only context")
        self.assertEqual(hinted_entry["gm_notes"], "GM only note")

    def test_lead_gm_sees_full_log(self):
        """Lead GM receives 200 with internal fields present."""
        self.client.force_authenticate(user=self.lead_gm_account)
        response = self.client.get(self._log_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        entries = response.data["entries"]
        beat_entries = [e for e in entries if e["entry_type"] == "beat_completion"]
        self.assertGreater(len(beat_entries), 0)

        hinted_entry = next(e for e in beat_entries if e["beat_id"] == self.hinted_beat.pk)
        # Lead GM sees internal fields
        self.assertEqual(hinted_entry["internal_description"], "GM-only context")
        self.assertEqual(hinted_entry["gm_notes"], "GM only note")

    # -------------------------------------------------------------------------
    # 200 path: player sees filtered log
    # -------------------------------------------------------------------------

    def test_player_sees_filtered_log(self):
        """Player receives 200; internal_description and gm_notes are absent."""
        self.client.force_authenticate(user=self.player_account)
        response = self.client.get(self._log_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        entries = response.data["entries"]
        beat_entries = [e for e in entries if e["entry_type"] == "beat_completion"]
        self.assertGreater(len(beat_entries), 0)

        for entry in beat_entries:
            self.assertIsNone(entry["internal_description"])
            self.assertIsNone(entry["gm_notes"])

    def test_player_secret_beat_hint_suppressed(self):
        """SECRET beat player_hint is empty string for player viewers."""
        self.client.force_authenticate(user=self.player_account)
        response = self.client.get(self._log_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        entries = response.data["entries"]
        beat_entries = [e for e in entries if e["entry_type"] == "beat_completion"]

        secret_entry = next((e for e in beat_entries if e["beat_id"] == self.secret_beat.pk), None)
        # SECRET beat appears (on completion) but player_hint is suppressed
        if secret_entry is not None:
            self.assertEqual(secret_entry["player_hint"], "")

    def test_player_sees_episode_resolution_entries(self):
        """Player can see episode_resolution entries in the log."""
        self.client.force_authenticate(user=self.player_account)
        response = self.client.get(self._log_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        entries = response.data["entries"]
        episode_entries = [e for e in entries if e["entry_type"] == "episode_resolution"]
        self.assertGreater(len(episode_entries), 0)

        ep_entry = episode_entries[0]
        self.assertIn("episode_id", ep_entry)
        self.assertIn("resolved_at", ep_entry)
        # Player does not see internal_notes
        self.assertIsNone(ep_entry["internal_notes"])

    # -------------------------------------------------------------------------
    # 403 path: no access
    # -------------------------------------------------------------------------

    def test_no_access_returns_403(self):
        """Outsider account with no relationship to the story gets 403."""
        self.client.force_authenticate(user=self.outsider_account)
        response = self.client.get(self._log_url())

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_returns_403(self):
        """Unauthenticated request gets 403 (IsStoryOwnerOrStaff denies unauthenticated)."""
        response = self.client.get(self._log_url())

        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

    # -------------------------------------------------------------------------
    # Response shape
    # -------------------------------------------------------------------------

    def test_response_has_entries_key(self):
        """Response JSON has a top-level 'entries' key."""
        self.client.force_authenticate(user=self.staff_account)
        response = self.client.get(self._log_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("entries", response.data)
        self.assertIsInstance(response.data["entries"], list)

    def test_beat_entry_shape(self):
        """Beat completion entries have the expected fields."""
        self.client.force_authenticate(user=self.staff_account)
        response = self.client.get(self._log_url())

        beat_entries = [e for e in response.data["entries"] if e["entry_type"] == "beat_completion"]
        self.assertGreater(len(beat_entries), 0)

        entry = beat_entries[0]
        for field in [
            "entry_type",
            "beat_id",
            "episode_id",
            "recorded_at",
            "outcome",
            "visibility",
            "player_hint",
            "player_resolution_text",
            "internal_description",
            "gm_notes",
        ]:
            self.assertIn(field, entry, f"Missing field: {field}")

    def test_episode_entry_shape(self):
        """Episode resolution entries have the expected fields."""
        self.client.force_authenticate(user=self.staff_account)
        response = self.client.get(self._log_url())

        ep_entries = [
            e for e in response.data["entries"] if e["entry_type"] == "episode_resolution"
        ]
        self.assertGreater(len(ep_entries), 0)

        entry = ep_entries[0]
        for field in [
            "entry_type",
            "episode_id",
            "episode_title",
            "resolved_at",
            "transition_id",
            "target_episode_id",
            "target_episode_title",
            "connection_type",
            "connection_summary",
            "internal_notes",
        ]:
            self.assertIn(field, entry, f"Missing field: {field}")
