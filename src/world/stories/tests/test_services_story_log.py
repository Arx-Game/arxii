"""Tests for world.stories.services.story_log and the viewer-role classifier.

Scenario: a CHARACTER-scope story with 2 chapters, 3 episodes, 4 beats
(HINTED, SECRET, VISIBLE, and a second HINTED beat), 3 BeatCompletions,
and 2 EpisodeResolutions.

Viewer tiers exercised:
- staff            → sees everything
- lead_gm          → sees everything (internal_description + gm_notes)
- player           → sees player-facing text; secrets suppressed pre-completion;
                     filtered to their own character's completions
- no_access / anon → empty list
"""

from __future__ import annotations

from evennia.utils.test_resources import EvenniaTestCase

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
from world.stories.permissions import classify_story_log_viewer_role
from world.stories.services.story_log import serialize_story_log
from world.stories.types import (
    LOG_ENTRY_BEAT_COMPLETION,
    LOG_ENTRY_EPISODE_RESOLUTION,
    StoryLogBeatEntry,
    StoryLogEpisodeEntry,
)


def _make_character_sheet_for_account(account):
    """Create a CharacterSheet whose ObjectDB character is owned by account.

    CharacterSheetFactory.primary_persona post-generation already creates a
    PRIMARY persona; no manual PersonaFactory call is needed.
    """
    char = CharacterFactory()
    char.db_account = account
    char.save()
    return CharacterSheetFactory(character=char)


class ClassifyStoryLogViewerRoleTests(EvenniaTestCase):
    """Unit tests for classify_story_log_viewer_role."""

    @classmethod
    def setUpTestData(cls):
        # Staff account
        cls.staff = AccountFactory(is_staff=True)

        # Lead GM setup: GMProfile + GMTable linked as story's primary_table
        cls.lead_gm_account = AccountFactory()
        cls.lead_gm_profile = GMProfileFactory(account=cls.lead_gm_account)
        cls.gm_table = GMTableFactory(gm=cls.lead_gm_profile)

        # CHARACTER-scope story with character belonging to player_account
        cls.player_account = AccountFactory()
        cls.player_sheet = _make_character_sheet_for_account(cls.player_account)

        cls.story = StoryFactory(
            scope=StoryScope.CHARACTER,
            character_sheet=cls.player_sheet,
            primary_table=cls.gm_table,
        )
        cls.progress = StoryProgressFactory(
            story=cls.story,
            character_sheet=cls.player_sheet,
        )

        # Unrelated account — no access
        cls.stranger = AccountFactory()

    def test_staff_returns_staff(self):
        """is_staff=True → 'staff' regardless of other factors."""
        role = classify_story_log_viewer_role(self.staff, self.story)
        self.assertEqual(role, "staff")

    def test_lead_gm_returns_lead_gm(self):
        """User with GMProfile whose table.gm matches story.primary_table → 'lead_gm'."""
        role = classify_story_log_viewer_role(self.lead_gm_account, self.story)
        self.assertEqual(role, "lead_gm")

    def test_character_owner_returns_player(self):
        """CHARACTER-scope: account whose character owns the story → 'player'."""
        role = classify_story_log_viewer_role(self.player_account, self.story, self.progress)
        self.assertEqual(role, "player")

    def test_unrelated_account_returns_no_access(self):
        """Account with no connection to the story → 'no_access'."""
        role = classify_story_log_viewer_role(self.stranger, self.story)
        self.assertEqual(role, "no_access")

    def test_staff_beats_lead_gm(self):
        """staff check fires before lead_gm check."""
        # Make a staff account that also happens to be the lead GM
        staff_gm_account = AccountFactory(is_staff=True)
        gm_profile = GMProfileFactory(account=staff_gm_account)
        table = GMTableFactory(gm=gm_profile)
        story = StoryFactory(scope=StoryScope.GLOBAL, primary_table=table)
        role = classify_story_log_viewer_role(staff_gm_account, story)
        self.assertEqual(role, "staff")

    def test_global_scope_any_authenticated_is_player(self):
        """GLOBAL-scope stories grant player-tier access to any authenticated user."""
        global_story = StoryFactory(scope=StoryScope.GLOBAL, primary_table=None)
        role = classify_story_log_viewer_role(self.stranger, global_story)
        self.assertEqual(role, "player")


class SerializeStoryLogTests(EvenniaTestCase):
    """Tests for serialize_story_log() — visibility filtering and ordering."""

    @classmethod
    def setUpTestData(cls):
        # Characters / accounts
        cls.player_account = AccountFactory()
        cls.player_sheet = _make_character_sheet_for_account(cls.player_account)

        cls.other_account = AccountFactory()
        cls.other_sheet = _make_character_sheet_for_account(cls.other_account)

        cls.staff_account = AccountFactory(is_staff=True)

        cls.lead_gm_account = AccountFactory()
        cls.lead_gm_profile = GMProfileFactory(account=cls.lead_gm_account)
        cls.gm_table = GMTableFactory(gm=cls.lead_gm_profile)

        # Story structure: story → chapter → 2 episodes
        cls.story = StoryFactory(
            scope=StoryScope.CHARACTER,
            character_sheet=cls.player_sheet,
            primary_table=cls.gm_table,
        )
        cls.progress = StoryProgressFactory(
            story=cls.story,
            character_sheet=cls.player_sheet,
        )
        chapter = ChapterFactory(story=cls.story, order=1)
        cls.ep1 = EpisodeFactory(chapter=chapter, order=1)
        cls.ep2 = EpisodeFactory(chapter=chapter, order=2)

        # 4 beats with different visibility settings
        cls.beat_hinted = BeatFactory(
            episode=cls.ep1,
            visibility=BeatVisibility.HINTED,
            player_hint="You sense something approaching.",
            player_resolution_text="The beast was slain.",
            internal_description="Secret: ancient dragon was the test.",
        )
        cls.beat_secret = BeatFactory(
            episode=cls.ep1,
            visibility=BeatVisibility.SECRET,
            player_hint="(hidden from player while active)",
            player_resolution_text="A hidden truth was revealed.",
            internal_description="Secret predicate: infiltrate the council.",
        )
        cls.beat_visible = BeatFactory(
            episode=cls.ep2,
            visibility=BeatVisibility.VISIBLE,
            player_hint="Defeat the warlord.",
            player_resolution_text="The warlord has fallen.",
            internal_description="Internal: warlord is actually a test construct.",
        )
        cls.beat_hinted2 = BeatFactory(
            episode=cls.ep2,
            visibility=BeatVisibility.HINTED,
            player_hint="Something stirs in the east.",
            player_resolution_text="The eastern threat was neutralized.",
            internal_description="Internal note: eastern army loyalty test.",
        )

        # 3 BeatCompletions for the player's character
        cls.comp_hinted = BeatCompletionFactory(
            beat=cls.beat_hinted,
            character_sheet=cls.player_sheet,
            outcome=BeatOutcome.SUCCESS,
            gm_notes="Well done!",
        )
        cls.comp_secret = BeatCompletionFactory(
            beat=cls.beat_secret,
            character_sheet=cls.player_sheet,
            outcome=BeatOutcome.SUCCESS,
            gm_notes="Secret completed.",
        )
        cls.comp_visible = BeatCompletionFactory(
            beat=cls.beat_visible,
            character_sheet=cls.player_sheet,
            outcome=BeatOutcome.SUCCESS,
            gm_notes="Visible beat done.",
        )

        # Another player's completion (should be hidden from player viewer)
        cls.other_comp = BeatCompletionFactory(
            beat=cls.beat_hinted2,
            character_sheet=cls.other_sheet,
            outcome=BeatOutcome.SUCCESS,
            gm_notes="Other player note.",
        )

        # 2 EpisodeResolutions for the player's character
        cls.trans = TransitionFactory(source_episode=cls.ep1, target_episode=cls.ep2)
        cls.res_ep1 = EpisodeResolutionFactory(
            episode=cls.ep1,
            character_sheet=cls.player_sheet,
            chosen_transition=cls.trans,
            gm_notes="Episode 1 resolved.",
        )
        cls.res_ep2 = EpisodeResolutionFactory(
            episode=cls.ep2,
            character_sheet=cls.player_sheet,
            chosen_transition=None,
            gm_notes="Episode 2 resolved — frontier.",
        )

    # ------------------------------------------------------------------
    # no_access
    # ------------------------------------------------------------------

    def test_no_access_returns_empty_list(self):
        """viewer_role='no_access' → empty list, no DB access."""
        result = serialize_story_log(
            story=self.story, progress=self.progress, viewer_role="no_access"
        )
        self.assertEqual(result, [])

    # ------------------------------------------------------------------
    # player visibility rules
    # ------------------------------------------------------------------

    def test_player_sees_hinted_beat_resolution_text(self):
        """Player sees HINTED beat's player_hint and player_resolution_text on completion."""
        entries = serialize_story_log(
            story=self.story, progress=self.progress, viewer_role="player"
        )
        beat_entries = [e for e in entries if isinstance(e, StoryLogBeatEntry)]
        hinted = next(e for e in beat_entries if e.beat_id == self.beat_hinted.pk)
        self.assertEqual(hinted.player_hint, self.beat_hinted.player_hint)
        self.assertEqual(hinted.player_resolution_text, self.beat_hinted.player_resolution_text)

    def test_player_does_not_see_internal_description(self):
        """Player viewer gets internal_description=None on all beat entries."""
        entries = serialize_story_log(
            story=self.story, progress=self.progress, viewer_role="player"
        )
        for entry in entries:
            if isinstance(entry, StoryLogBeatEntry):
                self.assertIsNone(
                    entry.internal_description,
                    f"Player should not see internal_description on beat {entry.beat_id}",
                )

    def test_player_does_not_see_gm_notes_on_beats(self):
        """Player viewer gets gm_notes=None on all beat entries."""
        entries = serialize_story_log(
            story=self.story, progress=self.progress, viewer_role="player"
        )
        for entry in entries:
            if isinstance(entry, StoryLogBeatEntry):
                self.assertIsNone(
                    entry.gm_notes,
                    f"Player should not see gm_notes on beat {entry.beat_id}",
                )

    def test_player_sees_secret_resolution_text_on_completion(self):
        """SECRET beats surface player_resolution_text on completion (author-controlled vagueness).

        The player_hint is suppressed (empty string) because SECRET beats should not
        reveal the hint retroactively. Only player_resolution_text is shown.
        """
        entries = serialize_story_log(
            story=self.story, progress=self.progress, viewer_role="player"
        )
        beat_entries = [e for e in entries if isinstance(e, StoryLogBeatEntry)]
        secret = next(e for e in beat_entries if e.beat_id == self.beat_secret.pk)
        # hint is suppressed for SECRET beats (player shouldn't see the original hint)
        self.assertEqual(secret.player_hint, "")
        # resolution text surfaces (author-controlled vagueness)
        self.assertEqual(secret.player_resolution_text, self.beat_secret.player_resolution_text)

    def test_player_sees_visible_beat_hints_and_resolution(self):
        """VISIBLE beat's player_hint and player_resolution_text both appear for player."""
        entries = serialize_story_log(
            story=self.story, progress=self.progress, viewer_role="player"
        )
        beat_entries = [e for e in entries if isinstance(e, StoryLogBeatEntry)]
        visible = next(e for e in beat_entries if e.beat_id == self.beat_visible.pk)
        self.assertEqual(visible.player_hint, self.beat_visible.player_hint)
        self.assertEqual(visible.player_resolution_text, self.beat_visible.player_resolution_text)

    def test_player_only_sees_own_completions(self):
        """Player viewer is scoped to their own character_sheet — other players' completions hidden.

        beat_hinted2 has only other_sheet's completion; player should NOT see it.
        """
        entries = serialize_story_log(
            story=self.story, progress=self.progress, viewer_role="player"
        )
        beat_entries = [e for e in entries if isinstance(e, StoryLogBeatEntry)]
        beat_ids = [e.beat_id for e in beat_entries]
        self.assertNotIn(
            self.beat_hinted2.pk,
            beat_ids,
            "Player should not see another character's beat completion",
        )

    def test_player_does_not_see_internal_notes_on_episode_entries(self):
        """Player viewer gets internal_notes=None on EpisodeResolution entries."""
        entries = serialize_story_log(
            story=self.story, progress=self.progress, viewer_role="player"
        )
        for entry in entries:
            if isinstance(entry, StoryLogEpisodeEntry):
                self.assertIsNone(
                    entry.internal_notes,
                    f"Player should not see internal_notes on episode {entry.episode_id}",
                )

    # ------------------------------------------------------------------
    # lead_gm visibility rules
    # ------------------------------------------------------------------

    def test_lead_gm_sees_internal_description(self):
        """Lead GM viewer gets all internal_descriptions populated."""
        entries = serialize_story_log(story=self.story, progress=None, viewer_role="lead_gm")
        beat_entries = [e for e in entries if isinstance(e, StoryLogBeatEntry)]
        hinted = next(e for e in beat_entries if e.beat_id == self.beat_hinted.pk)
        self.assertEqual(hinted.internal_description, self.beat_hinted.internal_description)

    def test_lead_gm_sees_gm_notes(self):
        """Lead GM viewer gets gm_notes on beat completion entries."""
        entries = serialize_story_log(story=self.story, progress=None, viewer_role="lead_gm")
        beat_entries = [e for e in entries if isinstance(e, StoryLogBeatEntry)]
        hinted = next(e for e in beat_entries if e.beat_id == self.beat_hinted.pk)
        self.assertEqual(hinted.gm_notes, self.comp_hinted.gm_notes)

    def test_lead_gm_sees_internal_notes_on_episode_entries(self):
        """Lead GM viewer gets gm_notes on EpisodeResolution entries."""
        entries = serialize_story_log(story=self.story, progress=None, viewer_role="lead_gm")
        episode_entries = [e for e in entries if isinstance(e, StoryLogEpisodeEntry)]
        ep1_entry = next(e for e in episode_entries if e.episode_id == self.ep1.pk)
        self.assertEqual(ep1_entry.internal_notes, self.res_ep1.gm_notes)

    def test_lead_gm_sees_all_completions_not_filtered_by_character(self):
        """Lead GM sees all completions regardless of which character (no progress filter)."""
        entries = serialize_story_log(story=self.story, progress=None, viewer_role="lead_gm")
        beat_entries = [e for e in entries if isinstance(e, StoryLogBeatEntry)]
        beat_ids = [e.beat_id for e in beat_entries]
        # Should include the other player's beat_hinted2 completion
        self.assertIn(self.beat_hinted2.pk, beat_ids)

    # ------------------------------------------------------------------
    # staff visibility rules
    # ------------------------------------------------------------------

    def test_staff_sees_everything(self):
        """Staff viewer gets all entries with all privileged fields populated."""
        entries = serialize_story_log(story=self.story, progress=None, viewer_role="staff")
        beat_entries = [e for e in entries if isinstance(e, StoryLogBeatEntry)]
        for entry in beat_entries:
            self.assertIsNotNone(entry.internal_description)
            self.assertIsNotNone(entry.gm_notes)

        episode_entries = [e for e in entries if isinstance(e, StoryLogEpisodeEntry)]
        for entry in episode_entries:
            self.assertIsNotNone(entry.internal_notes)

    # ------------------------------------------------------------------
    # chronological ordering
    # ------------------------------------------------------------------

    def test_entries_ordered_chronologically(self):
        """Mix of beat completions and episode resolutions is sorted by timestamp (oldest first)."""
        entries = serialize_story_log(story=self.story, progress=None, viewer_role="staff")
        timestamps = []
        for entry in entries:
            if isinstance(entry, StoryLogBeatEntry):
                timestamps.append(entry.recorded_at)
            else:
                timestamps.append(entry.resolved_at)

        self.assertEqual(
            timestamps,
            sorted(timestamps),
            "Story log entries should be ordered chronologically (oldest first)",
        )

    # ------------------------------------------------------------------
    # entry_type field
    # ------------------------------------------------------------------

    def test_beat_entries_have_correct_entry_type(self):
        """StoryLogBeatEntry.entry_type is always 'beat_completion'."""
        entries = serialize_story_log(story=self.story, progress=None, viewer_role="staff")
        for entry in entries:
            if isinstance(entry, StoryLogBeatEntry):
                self.assertEqual(entry.entry_type, LOG_ENTRY_BEAT_COMPLETION)

    def test_episode_entries_have_correct_entry_type(self):
        """StoryLogEpisodeEntry.entry_type is always 'episode_resolution'."""
        entries = serialize_story_log(story=self.story, progress=None, viewer_role="staff")
        for entry in entries:
            if isinstance(entry, StoryLogEpisodeEntry):
                self.assertEqual(entry.entry_type, LOG_ENTRY_EPISODE_RESOLUTION)

    # ------------------------------------------------------------------
    # transition data on episode entries
    # ------------------------------------------------------------------

    def test_episode_entry_with_transition_has_target_info(self):
        """EpisodeResolution with a chosen_transition populates target episode fields."""
        entries = serialize_story_log(story=self.story, progress=None, viewer_role="staff")
        episode_entries = [e for e in entries if isinstance(e, StoryLogEpisodeEntry)]
        ep1_entry = next(e for e in episode_entries if e.episode_id == self.ep1.pk)
        self.assertEqual(ep1_entry.transition_id, self.trans.pk)
        self.assertEqual(ep1_entry.target_episode_id, self.ep2.pk)
        self.assertEqual(ep1_entry.target_episode_title, self.ep2.title)

    def test_episode_entry_without_transition_has_null_target(self):
        """EpisodeResolution with no transition → frontier: target fields are None."""
        entries = serialize_story_log(story=self.story, progress=None, viewer_role="staff")
        episode_entries = [e for e in entries if isinstance(e, StoryLogEpisodeEntry)]
        ep2_entry = next(e for e in episode_entries if e.episode_id == self.ep2.pk)
        self.assertIsNone(ep2_entry.transition_id)
        self.assertIsNone(ep2_entry.target_episode_id)
        self.assertIsNone(ep2_entry.target_episode_title)
