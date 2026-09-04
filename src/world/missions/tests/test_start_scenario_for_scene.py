"""Tests for start_scenario_for_scene (#3565): the beat-run scenario starter
that starts (or rejoins) a beat's mission scenario for a whole scene's party.
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    ObjectDBFactory,
    RoomProfileFactory,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.missions.factories import MissionNodeFactory, MissionTemplateFactory
from world.missions.models import MissionInstance, MissionNode
from world.missions.services.run import gm_assign_mission, start_scenario_for_scene
from world.roster.factories import RosterTenureFactory
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.stories.factories import BeatFactory, ChapterFactory, EpisodeFactory, StoryFactory


def _make_room(label: str = "Room") -> tuple[object, object]:
    room = ObjectDBFactory(db_key=label, db_typeclass_path="typeclasses.rooms.Room")
    profile = RoomProfileFactory(objectdb=room)
    return room, profile


def _make_actor_with_account(db_key: str, room: object, account: object) -> tuple[object, object]:
    """Create a PC in *room* whose ``active_account`` is *account*.

    ``CharacterSheetFactory``'s post-generation hook wires a PRIMARY persona,
    and ``RosterTenureFactory`` wires the account -> player_data -> roster
    chain, so this character is a full member of ``active_participant_personas()``.
    """
    char = CharacterFactory(db_key=db_key, location=room)
    sheet = CharacterSheetFactory(character=char)
    entry = RosterTenureFactory(
        roster_entry__character_sheet=sheet,
        player_data__account=account,
        end_date=None,
    ).roster_entry
    return char, entry.character_sheet


def _make_template_with_entry():
    template = MissionTemplateFactory()
    MissionNodeFactory(template=template, key="entry", is_entry=True)
    return template


class StartScenarioForSceneTestBase(TestCase):
    """Shared fixture: a room+scene with two participant accounts, each puppeting
    a character with a wired PRIMARY persona, and a beat carrying a scenario.
    """

    def setUp(self) -> None:
        self.room, self.room_profile = _make_room("ScenarioRoom")

        self.account_a = AccountFactory(username="scenario_party_a")
        self.actor_a, self.sheet_a = _make_actor_with_account(
            "scenario_actor_a", self.room, self.account_a
        )

        self.account_b = AccountFactory(username="scenario_party_b")
        self.actor_b, self.sheet_b = _make_actor_with_account(
            "scenario_actor_b", self.room, self.account_b
        )

        self.scene = SceneFactory(location=self.room, is_active=True)
        SceneParticipationFactory(scene=self.scene, account=self.account_a, is_gm=False)
        SceneParticipationFactory(scene=self.scene, account=self.account_b, is_gm=False)

        self.story = StoryFactory()
        self.chapter = ChapterFactory(story=self.story)
        self.episode = EpisodeFactory(chapter=self.chapter)

        self.template = _make_template_with_entry()
        self.beat = BeatFactory(episode=self.episode, required_mission=self.template)


class StartScenarioForSceneTests(StartScenarioForSceneTestBase):
    def test_creates_instance_with_every_scene_participant(self) -> None:
        instance = start_scenario_for_scene(self.beat, self.scene)

        self.assertEqual(MissionInstance.objects.filter(source_beat=self.beat).count(), 1)
        self.assertEqual(instance.template_id, self.template.pk)

        participants = list(instance.participants.all())
        self.assertEqual(len(participants), 2)
        participant_ids = {p.character_id for p in participants}
        self.assertEqual(participant_ids, {self.sheet_a.pk, self.sheet_b.pk})
        holders = [p for p in participants if p.is_contract_holder]
        self.assertEqual(len(holders), 1)

        entry_node = MissionNode.objects.get(template=self.template, is_entry=True)
        self.assertEqual(instance.current_node_id, entry_node.pk)
        self.assertEqual(instance.anchor_room_id, self.room_profile.pk)

    def test_second_call_returns_same_instance_and_adds_newcomers(self) -> None:
        first = start_scenario_for_scene(self.beat, self.scene)

        account_c = AccountFactory(username="scenario_party_c")
        _actor_c, sheet_c = _make_actor_with_account("scenario_actor_c", self.room, account_c)
        SceneParticipationFactory(scene=self.scene, account=account_c, is_gm=False)

        second = start_scenario_for_scene(self.beat, self.scene)

        self.assertEqual(first.pk, second.pk)
        participant_ids = set(second.participants.values_list("character_id", flat=True))
        self.assertEqual(participant_ids, {self.sheet_a.pk, self.sheet_b.pk, sheet_c.pk})

    def test_reuses_instance_from_gm_assign_mission(self) -> None:
        assigned = gm_assign_mission(self.template, self.actor_a, beat=self.beat)

        instance = start_scenario_for_scene(self.beat, self.scene)

        self.assertEqual(assigned.pk, instance.pk)
        participant_ids = set(instance.participants.values_list("character_id", flat=True))
        self.assertEqual(participant_ids, {self.sheet_a.pk, self.sheet_b.pk})

    def test_beat_without_scenario_raises(self) -> None:
        beat = BeatFactory(episode=self.episode, required_mission=None)

        with self.assertRaises(ValueError):
            start_scenario_for_scene(beat, self.scene)

    def test_scene_with_no_participants_raises(self) -> None:
        empty_scene = SceneFactory(location=self.room, is_active=True)

        with self.assertRaises(ValueError):
            start_scenario_for_scene(self.beat, empty_scene)
