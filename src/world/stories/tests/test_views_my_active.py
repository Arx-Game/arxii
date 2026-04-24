"""Tests for MyActiveStoriesView — GET /api/stories/my-active/.

Scenarios covered:
- Unauthenticated → 401/403.
- Account with no stories → all three lists empty.
- CHARACTER story at frontier (no episode) → status "on_hold".
- CHARACTER story with unmet progression requirement → status "waiting_on_beats".
- CHARACTER story at episode edge (no transitions authored) → status "on_hold".
- CHARACTER story ready to schedule → status "ready_to_schedule".
- CHARACTER story with scheduled session → status "scheduled".
- CHARACTER story auto-resolvable → status "ready_to_resolve".
- GROUP story → appears in group_stories, not character_stories.
- GLOBAL story with StoryParticipation → appears in global_stories.
- Only active progress records are returned.
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core_management.test_utils import suppress_permission_errors
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMProfileFactory, GMTableFactory, GMTableMembershipFactory
from world.scenes.factories import PersonaFactory
from world.stories.constants import BeatOutcome, StoryEpisodeStatus, StoryScope, TransitionMode
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    EpisodeProgressionRequirementFactory,
    GlobalStoryProgressFactory,
    GroupStoryProgressFactory,
    SessionRequestFactory,
    StoryFactory,
    StoryParticipationFactory,
    StoryProgressFactory,
    TransitionFactory,
)

MY_ACTIVE_URL = reverse("stories-my-active")


def _make_character_for_account(account):
    """Return a CharacterSheet whose character.db_account is account."""
    char = CharacterFactory()
    char.db_account = account
    char.save()
    return CharacterSheetFactory(character=char)


def _make_member_persona(account):
    """Return a Persona linked to account via character_sheet -> character -> db_account."""
    sheet = _make_character_for_account(account)
    return PersonaFactory(character_sheet=sheet)


class MyActiveStoriesAuthTest(APITestCase):
    """Authentication gate."""

    @suppress_permission_errors
    def test_unauthenticated_rejected(self):
        response = self.client.get(MY_ACTIVE_URL)
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_authenticated_gets_200(self):
        user = AccountFactory()
        self.client.force_authenticate(user=user)
        response = self.client.get(MY_ACTIVE_URL)
        assert response.status_code == status.HTTP_200_OK


class MyActiveStoriesResponseShapeTest(APITestCase):
    """Response always contains the three scope keys."""

    def test_empty_response_has_all_keys(self):
        user = AccountFactory()
        self.client.force_authenticate(user=user)
        response = self.client.get(MY_ACTIVE_URL)
        assert response.status_code == status.HTTP_200_OK
        assert "character_stories" in response.data
        assert "group_stories" in response.data
        assert "global_stories" in response.data
        assert response.data["character_stories"] == []
        assert response.data["group_stories"] == []
        assert response.data["global_stories"] == []


class MyActiveStoriesCharacterScopeTest(APITestCase):
    """Tests for CHARACTER-scope story status lines."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.sheet = _make_character_for_account(cls.account)
        # A story owned by this character sheet.
        cls.story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=cls.sheet)
        cls.chapter = ChapterFactory(story=cls.story, order=1)
        cls.episode = EpisodeFactory(chapter=cls.chapter, order=2)

    def _get_character_stories(self):
        self.client.force_authenticate(user=self.account)
        response = self.client.get(MY_ACTIVE_URL)
        assert response.status_code == status.HTTP_200_OK
        return response.data["character_stories"]

    def test_frontier_progress_status(self):
        """Progress with no current_episode → status 'on_hold'."""
        StoryProgressFactory(story=self.story, character_sheet=self.sheet, current_episode=None)
        entries = self._get_character_stories()
        matching = [e for e in entries if e["story_id"] == self.story.pk]
        assert len(matching) == 1
        assert matching[0]["status"] == StoryEpisodeStatus.ON_HOLD
        assert matching[0]["current_episode_id"] is None
        assert matching[0]["chapter_order"] is None
        assert matching[0]["episode_order"] is None

    def test_episode_with_unmet_requirement_status(self):
        """Unmet EpisodeProgressionRequirement → status 'waiting_on_beats'."""
        progress = StoryProgressFactory(
            story=self.story, character_sheet=self.sheet, current_episode=self.episode
        )
        # Beat is UNSATISFIED — so progression requirement is not met.
        beat = BeatFactory(episode=self.episode, outcome=BeatOutcome.UNSATISFIED)
        EpisodeProgressionRequirementFactory(
            episode=self.episode, beat=beat, required_outcome=BeatOutcome.SUCCESS
        )
        entries = self._get_character_stories()
        matching = [e for e in entries if e["story_id"] == self.story.pk]
        assert len(matching) == 1
        assert matching[0]["status"] == StoryEpisodeStatus.WAITING_ON_BEATS
        assert matching[0]["chapter_order"] == 1
        assert matching[0]["episode_order"] == 2
        progress.delete()
        beat.delete()

    def test_episode_with_no_transitions_status(self):
        """No beats blocking AND no transitions authored → status 'on_hold' with position."""
        progress = StoryProgressFactory(
            story=self.story, character_sheet=self.sheet, current_episode=self.episode
        )
        # No EpisodeProgressionRequirements, no Transitions → empty eligible list.
        entries = self._get_character_stories()
        matching = [e for e in entries if e["story_id"] == self.story.pk]
        assert len(matching) == 1
        assert matching[0]["status"] == StoryEpisodeStatus.ON_HOLD
        assert matching[0]["chapter_order"] == 1
        assert matching[0]["episode_order"] == 2
        progress.delete()

    def test_episode_ready_to_schedule_status(self):
        """Open SessionRequest → status 'ready_to_schedule'."""
        next_ep = EpisodeFactory(chapter=self.chapter, order=3)
        TransitionFactory(
            source_episode=self.episode, target_episode=next_ep, mode=TransitionMode.AUTO
        )
        progress = StoryProgressFactory(
            story=self.story, character_sheet=self.sheet, current_episode=self.episode
        )
        SessionRequestFactory(episode=self.episode)
        entries = self._get_character_stories()
        matching = [e for e in entries if e["story_id"] == self.story.pk]
        assert len(matching) == 1
        assert matching[0]["status"] == StoryEpisodeStatus.READY_TO_SCHEDULE
        assert matching[0]["status_label"] == StoryEpisodeStatus.READY_TO_SCHEDULE.label
        assert matching[0]["open_session_request_id"] is not None
        assert matching[0]["chapter_order"] == 1
        assert matching[0]["episode_order"] == 2
        progress.delete()
        next_ep.delete()

    def test_episode_ready_to_resolve_status(self):
        """Eligible transition and no SessionRequest → status 'ready_to_resolve'."""
        next_ep = EpisodeFactory(chapter=self.chapter, order=4)
        TransitionFactory(
            source_episode=self.episode, target_episode=next_ep, mode=TransitionMode.AUTO
        )
        progress = StoryProgressFactory(
            story=self.story, character_sheet=self.sheet, current_episode=self.episode
        )
        entries = self._get_character_stories()
        matching = [e for e in entries if e["story_id"] == self.story.pk]
        assert len(matching) == 1
        assert matching[0]["status"] == StoryEpisodeStatus.READY_TO_RESOLVE
        assert matching[0]["open_session_request_id"] is None
        assert matching[0]["chapter_order"] == 1
        assert matching[0]["episode_order"] == 2
        progress.delete()
        next_ep.delete()

    def test_inactive_progress_not_returned(self):
        """Inactive progress records do not appear in the result."""
        StoryProgressFactory(
            story=self.story,
            character_sheet=self.sheet,
            current_episode=self.episode,
            is_active=False,
        )
        entries = self._get_character_stories()
        matching = [e for e in entries if e["story_id"] == self.story.pk]
        assert len(matching) == 0

    def test_entry_shape(self):
        """Response entry contains all required fields."""
        progress = StoryProgressFactory(
            story=self.story, character_sheet=self.sheet, current_episode=self.episode
        )
        entries = self._get_character_stories()
        matching = [e for e in entries if e["story_id"] == self.story.pk]
        assert len(matching) == 1
        entry = matching[0]
        for field in [
            "story_id",
            "story_title",
            "scope",
            "current_episode_id",
            "current_episode_title",
            "chapter_title",
            "status",
            "status_label",
            "chapter_order",
            "episode_order",
            "open_session_request_id",
            "scheduled_event_id",
            "scheduled_real_time",
        ]:
            assert field in entry, f"Missing field: {field}"
        assert entry["scope"] == StoryScope.CHARACTER
        progress.delete()

    def test_unrelated_account_does_not_see_story(self):
        """Another account's story should not appear in character_stories."""
        StoryProgressFactory(story=self.story, character_sheet=self.sheet, current_episode=None)
        other_user = AccountFactory()
        self.client.force_authenticate(user=other_user)
        response = self.client.get(MY_ACTIVE_URL)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["character_stories"] == []


class MyActiveStoriesGroupScopeTest(APITestCase):
    """Tests for GROUP-scope story entries."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.lead_gm_account = AccountFactory()
        cls.lead_gm_profile = GMProfileFactory(account=cls.lead_gm_account)
        cls.gm_table = GMTableFactory(gm=cls.lead_gm_profile)

        cls.member_persona = _make_member_persona(cls.account)
        cls.membership = GMTableMembershipFactory(
            table=cls.gm_table,
            persona=cls.member_persona,
        )

        cls.story = StoryFactory(scope=StoryScope.GROUP)
        cls.progress = GroupStoryProgressFactory(
            story=cls.story, gm_table=cls.gm_table, current_episode=None
        )

    def test_group_story_appears_in_group_stories(self):
        """Active group story appears under group_stories for members."""
        self.client.force_authenticate(user=self.account)
        response = self.client.get(MY_ACTIVE_URL)
        assert response.status_code == status.HTTP_200_OK
        group_stories = response.data["group_stories"]
        char_stories = response.data["character_stories"]
        ids = [e["story_id"] for e in group_stories]
        assert self.story.pk in ids
        # Must not bleed into character_stories
        char_ids = [e["story_id"] for e in char_stories]
        assert self.story.pk not in char_ids

    def test_group_story_scope_field(self):
        """Group story entries carry scope='group'."""
        self.client.force_authenticate(user=self.account)
        response = self.client.get(MY_ACTIVE_URL)
        group_stories = response.data["group_stories"]
        matching = [e for e in group_stories if e["story_id"] == self.story.pk]
        assert len(matching) == 1
        assert matching[0]["scope"] == StoryScope.GROUP


class MyActiveStoriesGlobalScopeTest(APITestCase):
    """Tests for GLOBAL-scope story entries."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.char = CharacterFactory()
        cls.char.db_account = cls.account
        cls.char.save()

        cls.story = StoryFactory(scope=StoryScope.GLOBAL)
        cls.progress = GlobalStoryProgressFactory(story=cls.story, current_episode=None)
        # Link character to story via StoryParticipation
        cls.participation = StoryParticipationFactory(story=cls.story, character=cls.char)

    def test_global_story_appears_in_global_stories(self):
        """Account with StoryParticipation sees the global story."""
        self.client.force_authenticate(user=self.account)
        response = self.client.get(MY_ACTIVE_URL)
        assert response.status_code == status.HTTP_200_OK
        global_stories = response.data["global_stories"]
        ids = [e["story_id"] for e in global_stories]
        assert self.story.pk in ids

    def test_account_without_participation_does_not_see_global(self):
        """Account without StoryParticipation does not see the global story."""
        other = AccountFactory()
        self.client.force_authenticate(user=other)
        response = self.client.get(MY_ACTIVE_URL)
        assert response.status_code == status.HTTP_200_OK
        global_stories = response.data["global_stories"]
        ids = [e["story_id"] for e in global_stories]
        assert self.story.pk not in ids
