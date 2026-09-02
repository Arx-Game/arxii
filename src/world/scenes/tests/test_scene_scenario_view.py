"""Tests for GET /api/scenes/{id}/scenario/ (#3565 task 7): the party's node and
the GM's ballots on the scene page.

Fixture pattern mirrors ``world.missions.tests.test_start_scenario_for_scene`` (a
room + scene with wired participant accounts) and ``test_gm_rail_views`` (the
story-standing gate): real ObjectDB rooms/characters via
``ObjectDBFactory``/``CharacterFactory`` (not deepcopyable), so per-test creation
in ``setUp`` is required.
"""

from __future__ import annotations

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.missions.constants import ConflictMode, OptionKind, OptionSource
from world.missions.factories import (
    MissionNodeFactory,
    MissionOptionFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionParticipant
from world.missions.services.play import submit_group_pick
from world.missions.services.run import start_scenario_for_scene
from world.roster.factories import RosterTenureFactory
from world.scenes.constants import ScenePrivacyMode
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.stories.factories import BeatFactory, ChapterFactory, EpisodeFactory, StoryFactory


def _make_room(label: str = "Room") -> object:
    return ObjectDBFactory(db_key=label, db_typeclass_path="typeclasses.rooms.Room")


def _make_actor_with_account(db_key: str, room: object, account: object) -> tuple[object, object]:
    """Create a PC in *room* whose active account is *account* (wires the roster
    chain so this character is a full member of ``active_participant_personas()``).
    """
    char = CharacterFactory(db_key=db_key, location=room)
    sheet = CharacterSheetFactory(character=char)
    RosterTenureFactory(
        roster_entry__character_sheet=sheet,
        player_data__account=account,
        end_date=None,
    )
    return char, sheet


class SceneScenarioViewTestBase(APITestCase):
    """A room+scene running a scenario for two participant accounts."""

    def setUp(self) -> None:
        self.room = _make_room("ScenarioRoom")

        self.account_a = AccountFactory(username="scenario_view_a")
        self.actor_a, self.sheet_a = _make_actor_with_account(
            "scenario_view_actor_a", self.room, self.account_a
        )
        self.account_b = AccountFactory(username="scenario_view_b")
        self.actor_b, self.sheet_b = _make_actor_with_account(
            "scenario_view_actor_b", self.room, self.account_b
        )

        self.scene = SceneFactory(location=self.room, is_active=True)
        SceneParticipationFactory(scene=self.scene, account=self.account_a, is_gm=False)
        SceneParticipationFactory(scene=self.scene, account=self.account_b, is_gm=False)

        self.story = StoryFactory()
        self.chapter = ChapterFactory(story=self.story)
        self.episode = EpisodeFactory(chapter=self.chapter)

        self.template = MissionTemplateFactory()
        self.entry_node = MissionNodeFactory(
            template=self.template,
            key="entry",
            is_entry=True,
            conflict_mode=ConflictMode.GROUP_VOTE,
        )
        self.option = MissionOptionFactory(
            node=self.entry_node,
            order=0,
            key="the-only-way",
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AUTHORED,
            authored_ic_framing="Push forward",
        )
        self.beat = BeatFactory(episode=self.episode, required_mission=self.template)

        self.instance = start_scenario_for_scene(self.beat, self.scene)
        self.scene.running_beat = self.beat
        self.scene.save(update_fields=["running_beat"])

        self.url = reverse("scene-scenario", kwargs={"pk": self.scene.pk})


class SceneScenarioViewTests(SceneScenarioViewTestBase):
    def test_participant_sees_own_group_beat_and_no_gm(self) -> None:
        self.client.force_authenticate(user=self.account_a)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["instance_id"], self.instance.pk)
        self.assertFalse(response.data["is_paused"])
        self.assertTrue(response.data["viewer_is_participant"])
        self.assertIsNone(response.data["gm"])
        group_beat = response.data["group_beat"]
        self.assertIsNotNone(group_beat)
        view = group_beat["group_beat"]
        self.assertIsNotNone(view)
        option_ids = [row["option_id"] for row in view["options"]]
        self.assertIn(self.option.pk, option_ids)

    def test_lead_gm_not_participant_sees_gm_ballots_and_no_group_beat(self) -> None:
        submit_group_pick(self.instance, self.actor_a, option_id=self.option.pk)

        gm_account = AccountFactory(username="scenario_view_gm")
        self.story.owners.add(gm_account)
        self.client.force_authenticate(user=gm_account)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["viewer_is_participant"])
        self.assertIsNone(response.data["group_beat"])
        gm = response.data["gm"]
        self.assertIsNotNone(gm)
        self.assertEqual(gm["node_key"], "entry")
        self.assertEqual(gm["conflict_mode"], ConflictMode.GROUP_VOTE)
        self.assertFalse(gm["is_paused"])
        ballot_character_ids = [row["character_id"] for row in gm["ballots"]]
        self.assertIn(self.sheet_a.pk, ballot_character_ids)
        self.assertEqual(gm["beat_outcome"], self.beat.outcome)
        self.assertEqual(gm["beat_outcome_key"], self.beat.outcome_key)

    def test_no_running_scenario_returns_null_instance(self) -> None:
        idle_scene = SceneFactory(location=self.room, is_active=True)
        SceneParticipationFactory(scene=idle_scene, account=self.account_a, is_gm=False)
        url = reverse("scene-scenario", kwargs={"pk": idle_scene.pk})
        self.client.force_authenticate(user=self.account_a)

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["instance_id"])
        self.assertFalse(response.data["is_paused"])
        self.assertFalse(response.data["viewer_is_participant"])
        self.assertIsNone(response.data["group_beat"])
        self.assertIsNone(response.data["gm"])

    def test_outsider_gets_200_with_both_sections_null(self) -> None:
        outsider = AccountFactory(username="scenario_view_outsider")
        self.client.force_authenticate(user=outsider)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["instance_id"], self.instance.pk)
        self.assertFalse(response.data["viewer_is_participant"])
        self.assertIsNone(response.data["group_beat"])
        self.assertIsNone(response.data["gm"])

    def test_unauthenticated_denied(self) -> None:
        response = self.client.get(self.url)
        self.assertIn(
            response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        )


class ScenePrivacyGateTests(SceneScenarioViewTestBase):
    """Fix round 1 CRITICAL: a PRIVATE scene's /scenario/ and /gm-rail/ state must
    not leak to an authenticated account with no standing on the scene (#3565).
    """

    def setUp(self) -> None:
        super().setUp()
        # A Room auto-creates a RoomProfile with is_public=True (typeclasses.rooms
        # .Room.at_object_creation); a PRIVATE scene there fails
        # Scene._validate_privacy_against_room's "publicly-listed room hosts only
        # PUBLIC scenes" invariant unless the room is de-listed first.
        room_profile = self.room.room_profile
        room_profile.is_public = False
        room_profile.save(update_fields=["is_public"])
        self.scene.privacy_mode = ScenePrivacyMode.PRIVATE
        self.scene.save(update_fields=["privacy_mode"])
        self.gm_rail_url = reverse("scene-gm-rail", kwargs={"pk": self.scene.pk})

    def test_outsider_denied_scenario_on_private_scene(self) -> None:
        outsider = AccountFactory(username="scenario_view_private_outsider")
        self.client.force_authenticate(user=outsider)

        response = self.client.get(self.url)

        self.assertIn(response.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))

    def test_outsider_denied_gm_rail_on_private_scene(self) -> None:
        outsider = AccountFactory(username="scenario_view_private_outsider_gm_rail")
        self.client.force_authenticate(user=outsider)

        response = self.client.get(self.gm_rail_url)

        self.assertIn(response.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))

    def test_participant_of_private_scene_still_sees_scenario(self) -> None:
        self.client.force_authenticate(user=self.account_a)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["viewer_is_participant"])
        self.assertIsNotNone(response.data["group_beat"])


class ViewerCharacterParticipantMatchingTests(SceneScenarioViewTestBase):
    """Fix round 1 IMPORTANT: an account with two active characters, only one of
    which is on the run, must still resolve to the one that is (#3565).

    ``PlayerData.account`` is a OneToOneField, so both tenures must share the
    SAME ``player_data`` row (a second ``RosterTenureFactory(player_data__account=
    account_c)`` call would try to create a second ``PlayerData`` for that account
    and violate the constraint) - fetch it after the first tenure and reuse it.
    """

    def test_second_character_on_run_still_resolves(self) -> None:
        account_c = AccountFactory(username="scenario_view_two_chars")
        actor_c1 = CharacterFactory(db_key="scenario_view_actor_c1", location=self.room)
        sheet_c1 = CharacterSheetFactory(character=actor_c1)
        now = timezone.now()
        # c1: the NEWER tenure (sorts first - RosterTenure.Meta.ordering is
        # "-start_date") but never joins the run.
        RosterTenureFactory(
            roster_entry__character_sheet=sheet_c1,
            player_data__account=account_c,
            end_date=None,
            start_date=now,
        )
        player_data = account_c.player_data

        actor_c2 = CharacterFactory(db_key="scenario_view_actor_c2", location=self.room)
        sheet_c2 = CharacterSheetFactory(character=actor_c2)
        # c2: the OLDER tenure (sorts second) but IS a MissionParticipant on the
        # already-running instance.
        RosterTenureFactory(
            roster_entry__character_sheet=sheet_c2,
            player_data=player_data,
            end_date=None,
            start_date=now - timedelta(days=1),
        )
        MissionParticipant.objects.create(
            instance=self.instance, character=sheet_c2, is_contract_holder=False
        )
        SceneParticipationFactory(scene=self.scene, account=account_c, is_gm=False)

        self.client.force_authenticate(user=account_c)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["viewer_is_participant"])
        self.assertIsNotNone(response.data["group_beat"])
