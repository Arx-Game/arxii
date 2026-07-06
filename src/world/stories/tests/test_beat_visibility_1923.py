"""Tests for BeatViewSet list visibility scoping (#1923).

Covers the security gap where ``BeatViewSet.list()`` had no queryset-level
story-visibility filter: any authenticated user could enumerate every beat of
any episode — including SECRET beats and the GM-only ``internal_description``
field — regardless of story privacy or participation.

The fix adds ``BeatViewSet.get_queryset()`` (mirroring
``IsStoryOwnerOrStaff._can_read_story`` at the queryset level) and gates
``internal_description`` in ``BeatSerializer.to_representation``.
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.stories.constants import BeatVisibility
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    PrivateStoryFactory,
    StoryFactory,
    StoryParticipationFactory,
)


def _character_with_account(account):
    """Return an ObjectDB character whose ``db_account`` is ``account``."""
    char = CharacterFactory()
    char.db_account = account
    char.save()
    return char


class BeatListVisibilityTest(APITestCase):
    """``GET /api/beats/`` must only surface beats the viewer may read."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)

        # --- PRIVATE story with two beats (one VISIBLE, one SECRET) ---
        cls.owner = AccountFactory()
        cls.private_story = PrivateStoryFactory(owners=[cls.owner])
        cls.private_chapter = ChapterFactory(story=cls.private_story)
        cls.private_episode = EpisodeFactory(chapter=cls.private_chapter)
        cls.private_visible_beat = BeatFactory(
            episode=cls.private_episode,
            visibility=BeatVisibility.VISIBLE,
            internal_description="GM-only private beat detail",
        )
        cls.private_secret_beat = BeatFactory(
            episode=cls.private_episode,
            visibility=BeatVisibility.SECRET,
            internal_description="GM-only secret beat detail",
        )

        # A non-owner, non-participant account.
        cls.outsider = AccountFactory()

        # An active participant in the private story.
        cls.participant = AccountFactory()
        cls.participant_char = _character_with_account(cls.participant)
        cls.participation = StoryParticipationFactory(
            story=cls.private_story,
            character=cls.participant_char,
            is_active=True,
            trusted_by_owner=False,
        )

    # --- queryset scoping -------------------------------------------------

    def test_outsider_cannot_list_private_story_beats(self):
        """A non-owner/non-participant sees no beats from a PRIVATE story."""
        self.client.force_authenticate(user=self.outsider)
        response = self.client.get(reverse("beat-list"))
        assert response.status_code == status.HTTP_200_OK
        beat_ids = {b["id"] for b in response.data["results"]}
        assert self.private_visible_beat.id not in beat_ids
        assert self.private_secret_beat.id not in beat_ids

    def test_owner_can_list_private_story_beats(self):
        """The story owner sees non-SECRET beats of their private story."""
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(reverse("beat-list"))
        assert response.status_code == status.HTTP_200_OK
        beat_ids = {b["id"] for b in response.data["results"]}
        assert self.private_visible_beat.id in beat_ids

    def test_participant_can_list_private_story_beats(self):
        """An active participant sees non-SECRET beats of the private story."""
        self.client.force_authenticate(user=self.participant)
        response = self.client.get(reverse("beat-list"))
        assert response.status_code == status.HTTP_200_OK
        beat_ids = {b["id"] for b in response.data["results"]}
        assert self.private_visible_beat.id in beat_ids

    def test_staff_sees_all_beats_including_secret(self):
        """Staff bypass the queryset filter entirely, including SECRET beats."""
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(reverse("beat-list"))
        assert response.status_code == status.HTTP_200_OK
        beat_ids = {b["id"] for b in response.data["results"]}
        assert self.private_visible_beat.id in beat_ids
        assert self.private_secret_beat.id in beat_ids

    # --- SECRET beat exclusion -------------------------------------------

    def test_non_staff_never_sees_secret_beats(self):
        """SECRET beats are excluded from list for every non-staff viewer."""
        for user in (self.owner, self.participant):
            self.client.force_authenticate(user=user)
            response = self.client.get(reverse("beat-list"))
            beat_ids = {b["id"] for b in response.data["results"]}
            assert self.private_secret_beat.id not in beat_ids

    def test_episode_filter_still_scoped(self):
        """``?episode=<id>`` does not bypass the visibility filter."""
        self.client.force_authenticate(user=self.outsider)
        url = reverse("beat-list")
        response = self.client.get(url, {"episode": self.private_episode.id})
        assert response.status_code == status.HTTP_200_OK
        assert response.data["results"] == []


class BeatInternalDescriptionGateTest(APITestCase):
    """``internal_description`` must not leak to non-privileged viewers."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.owner = AccountFactory()
        cls.outsider = AccountFactory()

        # PUBLIC story so the outsider *can* see the beat — the test is
        # about the field-level gate, not queryset scoping.
        cls.story = StoryFactory(owners=[cls.owner])
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter)
        cls.beat = BeatFactory(
            episode=cls.episode,
            visibility=BeatVisibility.VISIBLE,
            internal_description="GM-only secret predicate detail",
        )

    def test_staff_sees_internal_description(self):
        self.client.force_authenticate(user=self.staff)
        url = reverse("beat-detail", kwargs={"pk": self.beat.pk})
        response = self.client.get(url)
        assert response.data["internal_description"] == "GM-only secret predicate detail"

    def test_owner_sees_internal_description(self):
        self.client.force_authenticate(user=self.owner)
        url = reverse("beat-detail", kwargs={"pk": self.beat.pk})
        response = self.client.get(url)
        assert response.data["internal_description"] == "GM-only secret predicate detail"

    def test_outsider_does_not_see_internal_description(self):
        """A non-owner (even of a PUBLIC story) gets ``None``."""
        self.client.force_authenticate(user=self.outsider)
        url = reverse("beat-detail", kwargs={"pk": self.beat.pk})
        response = self.client.get(url)
        assert response.data["internal_description"] is None

    def test_internal_description_stripped_in_list_too(self):
        """The field-level gate applies on list, not just retrieve."""
        self.client.force_authenticate(user=self.outsider)
        response = self.client.get(reverse("beat-list"))
        assert response.status_code == status.HTTP_200_OK
        for beat in response.data["results"]:
            if beat["id"] == self.beat.id:
                assert beat["internal_description"] is None
                return
        msg = "beat not found in list results"
        raise AssertionError(msg)
