"""Tests for NPC guard assignment actions (#2178)."""

from unittest.mock import patch

from django.test import TestCase

from actions.registry import get_action
from evennia_extensions.factories import CharacterFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.npc_services.factories import FunctionaryFactory
from world.npc_services.models import AssignmentRole, NPCAssignment


class AssignmentActionRegistryTests(TestCase):
    def test_assign_guard_action_registered(self):
        assert get_action("assign_guard") is not None

    def test_unassign_guard_action_registered(self):
        assert get_action("unassign_guard") is not None

    def test_list_guard_assignments_action_registered(self):
        assert get_action("list_guard_assignments") is not None

    # #2989 — servant + doorman assignment mirrors.
    def test_assign_servant_action_registered(self):
        assert get_action("assign_servant") is not None

    def test_unassign_servant_action_registered(self):
        assert get_action("unassign_servant") is not None

    def test_list_servant_assignments_action_registered(self):
        assert get_action("list_servant_assignments") is not None

    def test_assign_doorman_action_registered(self):
        assert get_action("assign_doorman") is not None

    def test_unassign_doorman_action_registered(self):
        assert get_action("unassign_doorman") is not None

    def test_list_doorman_assignments_action_registered(self):
        assert get_action("list_doorman_assignments") is not None


class AssignServantDoormanActionTests(TestCase):
    """Functional execute() tests for the #2989 SERVANT/DOORMAN action mirrors.

    ``is_owner`` is mocked (mirrors ``test_servant_fetch.py`` — the real
    AreaClosure walk is Postgres-only) so these stay in the fast SQLite tier.
    """

    def setUp(self) -> None:
        self.room_profile = RoomProfileFactory()
        self.room = self.room_profile.objectdb
        self.actor = CharacterFactory(db_key="Owner", location=self.room)
        self.sheet = CharacterSheetFactory(character=self.actor)
        self.persona = self.sheet.primary_persona
        self.func = FunctionaryFactory(room=self.room_profile)

    def _run(self, key: str, **kwargs):
        with (
            patch("world.locations.services.is_owner", return_value=True),
            patch(
                "world.scenes.services.active_persona_for_sheet",
                return_value=self.persona,
            ),
        ):
            return get_action(key).run(self.actor, **kwargs)

    def test_assign_servant_creates_active_assignment(self):
        result = self._run("assign_servant", source_type="functionary", npc_id=self.func.pk)
        self.assertTrue(result.success)
        assignment = NPCAssignment.objects.get(
            room=self.room_profile, assignment_role=AssignmentRole.SERVANT
        )
        self.assertTrue(assignment.is_active)

    def test_assign_doorman_creates_active_assignment(self):
        result = self._run("assign_doorman", source_type="functionary", npc_id=self.func.pk)
        self.assertTrue(result.success)
        assignment = NPCAssignment.objects.get(
            room=self.room_profile, assignment_role=AssignmentRole.DOORMAN
        )
        self.assertTrue(assignment.is_active)

    def test_servant_and_doorman_coexist(self):
        """Assigning SERVANT doesn't retire an active DOORMAN in the same room."""
        self._run("assign_doorman", source_type="functionary", npc_id=self.func.pk)
        other_func = FunctionaryFactory(room=self.room_profile)
        self._run("assign_servant", source_type="functionary", npc_id=other_func.pk)

        self.assertTrue(
            NPCAssignment.objects.filter(
                room=self.room_profile, assignment_role=AssignmentRole.DOORMAN, is_active=True
            ).exists()
        )
        self.assertTrue(
            NPCAssignment.objects.filter(
                room=self.room_profile, assignment_role=AssignmentRole.SERVANT, is_active=True
            ).exists()
        )

    def test_unassign_servant_retires_assignment(self):
        self._run("assign_servant", source_type="functionary", npc_id=self.func.pk)
        result = self._run("unassign_servant")
        self.assertTrue(result.success)
        self.assertFalse(
            NPCAssignment.objects.filter(
                room=self.room_profile, assignment_role=AssignmentRole.SERVANT, is_active=True
            ).exists()
        )

    def test_unassign_doorman_with_none_active_fails(self):
        result = self._run("unassign_doorman")
        self.assertFalse(result.success)

    def test_list_servant_assignments_reports_active(self):
        self._run("assign_servant", source_type="functionary", npc_id=self.func.pk)
        result = self._run("list_servant_assignments")
        self.assertTrue(result.success)
        self.assertEqual(len(result.data["assignments"]), 1)

    def test_non_owner_cannot_assign_servant(self):
        with (
            patch("world.locations.services.is_owner", return_value=False),
            patch(
                "world.scenes.services.active_persona_for_sheet",
                return_value=self.persona,
            ),
        ):
            result = get_action("assign_servant").run(
                self.actor, source_type="functionary", npc_id=self.func.pk
            )
        self.assertFalse(result.success)
        self.assertFalse(
            NPCAssignment.objects.filter(
                room=self.room_profile, assignment_role=AssignmentRole.SERVANT
            ).exists()
        )
