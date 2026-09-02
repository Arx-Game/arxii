"""Tests for GET /api/scenes/{id}/scenario/ (#3565 task 7): the party's node and
the GM's ballots on the scene page.

Fixture pattern mirrors ``world.missions.tests.test_start_scenario_for_scene`` (a
room + scene with wired participant accounts) and ``test_gm_rail_views`` (the
story-standing gate): real ObjectDB rooms/characters via
``ObjectDBFactory``/``CharacterFactory`` (not deepcopyable), so per-test creation
in ``setUp`` is required.
"""

from __future__ import annotations

from django.urls import reverse
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
from world.missions.services.play import submit_group_pick
from world.missions.services.run import start_scenario_for_scene
from world.roster.factories import RosterTenureFactory
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
