"""Tests for #1023 — clean player mission abandon.

Covers the `play.abandon_mission` service (contract-holder gate, terminal
write, slot-freeing, spawned-room teardown) and the `MissionJournalViewSet`
`abandon` action (200 / 400 / 404).
"""

from __future__ import annotations

from unittest import mock

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    ObjectDBFactory,
    RoomProfileFactory,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.missions.constants import MissionStatus, OptionKind, OptionSource
from world.missions.factories import (
    MissionNodeFactory,
    MissionOptionFactory,
    MissionParticipantFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionInstance
from world.missions.services.play import (
    AbandonMissionError,
    NotParticipantError,
    abandon_mission,
)
from world.missions.services.run import staff_assign_mission


def _room(name: str):
    room = ObjectDBFactory(db_key=name, db_typeclass_path="typeclasses.rooms.Room")
    profile = RoomProfileFactory(objectdb=room)
    return room, profile


def _pc():
    character = CharacterFactory()
    CharacterSheetFactory(character=character)
    return character


def _graph(name: str):
    """Entry node → one BRANCH option to a terminal second node."""
    template = MissionTemplateFactory(name=name)
    entry = MissionNodeFactory(template=template, key="entry", is_entry=True)
    second = MissionNodeFactory(template=template, key="second")
    MissionOptionFactory(
        node=entry,
        option_kind=OptionKind.BRANCH,
        source_kind=OptionSource.AUTHORED,
        authored_ic_framing="PLACEHOLDER take the first step",
        branch_target=second,
    )
    return template


def _assigned_active():
    """A freshly staff-assigned ACTIVE run + its contract-holder character."""
    character = _pc()
    instance = staff_assign_mission(_graph("abandon-me"), character)
    return instance, character


class AbandonMissionServiceTests(TestCase):
    def test_contract_holder_abandons_active(self):
        instance, character = _assigned_active()
        self.assertEqual(instance.status, MissionStatus.ACTIVE)
        abandon_mission(instance, character)
        instance.refresh_from_db()
        self.assertEqual(instance.status, MissionStatus.ABANDONED)
        self.assertIsNotNone(instance.completed_at)
        self.assertIsNone(instance.current_node_id)

    def test_abandon_frees_active_slot(self):
        instance, character = _assigned_active()
        abandon_mission(instance, character)
        still_active = MissionInstance.objects.filter(
            participants__character=character,
            status=MissionStatus.ACTIVE,
        ).count()
        self.assertEqual(still_active, 0)

    def test_non_contract_holder_cannot_abandon(self):
        instance, _ = _assigned_active()
        other = _pc()
        MissionParticipantFactory(instance=instance, character=other, is_contract_holder=False)
        with self.assertRaises(AbandonMissionError):
            abandon_mission(instance, other)
        instance.refresh_from_db()
        self.assertEqual(instance.status, MissionStatus.ACTIVE)

    def test_non_participant_raises(self):
        instance, _ = _assigned_active()
        with self.assertRaises(NotParticipantError):
            abandon_mission(instance, _pc())

    def test_already_terminal_cannot_be_abandoned(self):
        instance, character = _assigned_active()
        abandon_mission(instance, character)
        instance.refresh_from_db()
        with self.assertRaises(AbandonMissionError):
            abandon_mission(instance, character)

    def test_spawned_room_torn_down(self):
        instance, character = _assigned_active()
        room, profile = _room("Instanced Vault")
        instance.spawned_room = profile
        instance.save(update_fields=["spawned_room"])
        with mock.patch("world.instances.services.complete_instanced_room") as teardown:
            abandon_mission(instance, character)
        teardown.assert_called_once_with(room)

    def test_no_spawned_room_skips_teardown(self):
        instance, character = _assigned_active()
        with mock.patch("world.instances.services.complete_instanced_room") as teardown:
            abandon_mission(instance, character)
        teardown.assert_not_called()


class AbandonMissionAPITests(TestCase):
    def setUp(self):
        self.account = AccountFactory()
        self.character = _pc()
        self.instance = staff_assign_mission(_graph("api-abandon"), self.character)
        self.client = APIClient()
        self.client.force_authenticate(self.account)

    def _post_abandon(self, as_character):
        with mock.patch("world.missions.views._puppet_character", return_value=as_character):
            return self.client.post(f"/api/missions/journal/{self.instance.pk}/abandon/")

    def test_contract_holder_abandon_returns_200(self):
        res = self._post_abandon(self.character)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["id"], self.instance.pk)
        self.assertEqual(res.data["status"], MissionStatus.ABANDONED.value)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.status, MissionStatus.ABANDONED)

    def test_non_participant_gets_404(self):
        res = self._post_abandon(_pc())
        self.assertEqual(res.status_code, 404)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.status, MissionStatus.ACTIVE)

    def test_non_contract_holder_gets_400(self):
        other = _pc()
        MissionParticipantFactory(instance=self.instance, character=other, is_contract_holder=False)
        res = self._post_abandon(other)
        self.assertEqual(res.status_code, 400)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.status, MissionStatus.ACTIVE)
