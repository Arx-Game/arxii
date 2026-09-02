"""Tests for GET /api/scenes/{id}/stakes-summary/ (#3561 task 8): the party's
opt-in read for what the scene's running beat wagers.

Fixture pattern mirrors ``test_scene_scenario_view.py`` (a room + scene with
wired participant accounts): real ObjectDB rooms/characters via
``ObjectDBFactory``/``CharacterFactory`` (not deepcopyable), so per-test
creation in ``setUp`` is required.
"""

from __future__ import annotations

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import RosterTenureFactory
from world.scenes.constants import ScenePrivacyMode
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.stories.constants import StakeSeverity
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    StakeFactory,
    StoryFactory,
)


def _make_room(label: str = "Room") -> object:
    return ObjectDBFactory(db_key=label, db_typeclass_path="typeclasses.rooms.Room")


def _make_actor_with_account(db_key: str, room: object, account: object) -> tuple[object, object]:
    """Create a PC in *room* whose active account is *account*."""
    char = CharacterFactory(db_key=db_key, location=room)
    sheet = CharacterSheetFactory(character=char)
    RosterTenureFactory(
        roster_entry__character_sheet=sheet,
        player_data__account=account,
        end_date=None,
    )
    return char, sheet


class SceneStakesSummaryViewTests(APITestCase):
    """A room+scene running a staked beat, one participant account, one outsider."""

    def setUp(self) -> None:
        self.room = _make_room("StakesSummaryRoom")

        self.account_a = AccountFactory(username="stakes_summary_view_a")
        self.actor_a, self.sheet_a = _make_actor_with_account(
            "stakes_summary_view_actor_a", self.room, self.account_a
        )

        self.scene = SceneFactory(location=self.room, is_active=True)
        SceneParticipationFactory(scene=self.scene, account=self.account_a, is_gm=False)

        self.story = StoryFactory()
        self.chapter = ChapterFactory(story=self.story)
        self.episode = EpisodeFactory(chapter=self.chapter)
        self.beat = BeatFactory(episode=self.episode)
        self.stake = StakeFactory(
            beat=self.beat,
            player_summary="A dueling scar, worn for all to see.",
            severity=StakeSeverity.GRAVE,
        )

        self.scene.running_beat = self.beat
        self.scene.save(update_fields=["running_beat"])

        self.url = reverse("scene-stakes-summary", kwargs={"pk": self.scene.pk})

    def test_participant_sees_the_wager(self) -> None:
        self.client.force_authenticate(user=self.account_a)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["declared_risk"], self.beat.risk)
        self.assertTrue(response.data["is_ready"])
        stakes = response.data["stakes"]
        self.assertEqual(len(stakes), 1)
        self.assertEqual(stakes[0]["id"], self.stake.pk)
        self.assertEqual(stakes[0]["player_summary"], "A dueling scar, worn for all to see.")
        self.assertEqual(stakes[0]["severity"], StakeSeverity.GRAVE)

    def test_never_leaks_a_resolution_or_branch_key(self) -> None:
        self.client.force_authenticate(user=self.account_a)

        response = self.client.get(self.url)

        stake_payload = response.data["stakes"][0]
        for leaked_key in (
            "resolution",
            "resolutions",
            "narrative_summary",
            "outcome_key",
            "column",
            "escalates_to_risk",
        ):
            self.assertNotIn(leaked_key, stake_payload)

    def test_no_running_beat_returns_the_empty_shape(self) -> None:
        idle_scene = SceneFactory(location=self.room, is_active=True)
        SceneParticipationFactory(scene=idle_scene, account=self.account_a, is_gm=False)
        url = reverse("scene-stakes-summary", kwargs={"pk": idle_scene.pk})
        self.client.force_authenticate(user=self.account_a)

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["declared_risk"])
        self.assertIsNone(response.data["effective_risk"])
        self.assertTrue(response.data["is_ready"])
        self.assertEqual(response.data["stakes"], [])

    def test_unauthenticated_denied(self) -> None:
        response = self.client.get(self.url)
        self.assertIn(
            response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        )


class SceneStakesSummaryPrivacyGateTests(APITestCase):
    """An outsider with no standing on a PRIVATE scene must not reach its
    stakes summary (mirrors ``ScenePrivacyGateTests`` for /scenario/ and
    /gm-rail/, #3565 fix round 1's leak invariant).
    """

    def setUp(self) -> None:
        self.room = _make_room("StakesSummaryPrivacyRoom")
        room_profile = self.room.room_profile
        room_profile.is_public = False
        room_profile.save(update_fields=["is_public"])

        self.account_a = AccountFactory(username="stakes_summary_privacy_a")
        self.actor_a, self.sheet_a = _make_actor_with_account(
            "stakes_summary_privacy_actor_a", self.room, self.account_a
        )

        self.scene = SceneFactory(
            location=self.room, is_active=True, privacy_mode=ScenePrivacyMode.PRIVATE
        )
        SceneParticipationFactory(scene=self.scene, account=self.account_a, is_gm=False)

        self.story = StoryFactory()
        self.chapter = ChapterFactory(story=self.story)
        self.episode = EpisodeFactory(chapter=self.chapter)
        self.beat = BeatFactory(episode=self.episode)
        StakeFactory(beat=self.beat)
        self.scene.running_beat = self.beat
        self.scene.save(update_fields=["running_beat"])

        self.url = reverse("scene-stakes-summary", kwargs={"pk": self.scene.pk})

    def test_outsider_denied_on_private_scene(self) -> None:
        outsider = AccountFactory(username="stakes_summary_privacy_outsider")
        self.client.force_authenticate(user=outsider)

        response = self.client.get(self.url)

        self.assertIn(response.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))

    def test_participant_of_private_scene_still_sees_the_wager(self) -> None:
        self.client.force_authenticate(user=self.account_a)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["stakes"]), 1)
