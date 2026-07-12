"""Tests for the NPCAssignment model (#2178)."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from world.npc_services.models import (
    AssignmentRole,
    NPCAssignment,
    NPCSourceType,
)


class NPCAssignmentModelTests(TestCase):
    def test_clean_requires_exactly_one_source(self):
        """Neither FK set → validation error."""
        from evennia_extensions.factories import RoomProfileFactory
        from world.scenes.factories import PersonaFactory

        assignment = NPCAssignment(
            source_type=NPCSourceType.FUNCTIONARY,
            functionary=None,
            npc_asset=None,
            room=RoomProfileFactory(),
            assignment_role=AssignmentRole.GUARD,
            assigned_by=PersonaFactory(),
        )
        with self.assertRaises(ValidationError):
            assignment.clean()

    def test_clean_rejects_both_sources_set(self):
        """Both FKs set → validation error."""
        from evennia_extensions.factories import RoomProfileFactory
        from world.assets.factories import NPCAssetFactory
        from world.npc_services.factories import FunctionaryFactory
        from world.scenes.factories import PersonaFactory

        assignment = NPCAssignment(
            source_type=NPCSourceType.FUNCTIONARY,
            functionary=FunctionaryFactory(),
            npc_asset=NPCAssetFactory(),
            room=RoomProfileFactory(),
            assignment_role=AssignmentRole.GUARD,
            assigned_by=PersonaFactory(),
        )
        with self.assertRaises(ValidationError):
            assignment.clean()

    def test_clean_accepts_functionary_source(self):
        from evennia_extensions.factories import RoomProfileFactory
        from world.npc_services.factories import FunctionaryFactory
        from world.scenes.factories import PersonaFactory

        assignment = NPCAssignment(
            source_type=NPCSourceType.FUNCTIONARY,
            functionary=FunctionaryFactory(),
            room=RoomProfileFactory(),
            assignment_role=AssignmentRole.GUARD,
            assigned_by=PersonaFactory(),
        )
        assignment.clean()  # should not raise

    def test_clean_accepts_npc_asset_source(self):
        from evennia_extensions.factories import RoomProfileFactory
        from world.assets.factories import NPCAssetFactory
        from world.scenes.factories import PersonaFactory

        assignment = NPCAssignment(
            source_type=NPCSourceType.NPC_ASSET,
            npc_asset=NPCAssetFactory(),
            room=RoomProfileFactory(),
            assignment_role=AssignmentRole.GUARD,
            assigned_by=PersonaFactory(),
        )
        assignment.clean()  # should not raise

    def test_unique_active_guard_per_room(self):
        """Two active GUARD assignments for same room → IntegrityError."""
        from evennia_extensions.factories import RoomProfileFactory
        from world.npc_services.factories import FunctionaryFactory
        from world.scenes.factories import PersonaFactory

        room = RoomProfileFactory()
        persona = PersonaFactory()
        NPCAssignment.objects.create(
            source_type=NPCSourceType.FUNCTIONARY,
            functionary=FunctionaryFactory(room=room),
            room=room,
            assignment_role=AssignmentRole.GUARD,
            assigned_by=persona,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                NPCAssignment.objects.create(
                    source_type=NPCSourceType.FUNCTIONARY,
                    functionary=FunctionaryFactory(room=room),
                    room=room,
                    assignment_role=AssignmentRole.GUARD,
                    assigned_by=persona,
                )

    def test_inactive_assignment_does_not_collide(self):
        """Ended assignment + new active assignment for same room → OK."""
        from evennia_extensions.factories import RoomProfileFactory
        from world.npc_services.factories import FunctionaryFactory
        from world.scenes.factories import PersonaFactory

        room = RoomProfileFactory()
        persona = PersonaFactory()
        old = NPCAssignment.objects.create(
            source_type=NPCSourceType.FUNCTIONARY,
            functionary=FunctionaryFactory(room=room),
            room=room,
            assignment_role=AssignmentRole.GUARD,
            assigned_by=persona,
        )
        old.is_active = False
        old.save()
        # New active assignment should succeed
        NPCAssignment.objects.create(
            source_type=NPCSourceType.FUNCTIONARY,
            functionary=FunctionaryFactory(room=room),
            room=room,
            assignment_role=AssignmentRole.GUARD,
            assigned_by=persona,
        )

    def test_get_active_target_returns_functionary(self):
        from evennia_extensions.factories import RoomProfileFactory
        from world.npc_services.factories import FunctionaryFactory
        from world.scenes.factories import PersonaFactory

        func = FunctionaryFactory()
        assignment = NPCAssignment.objects.create(
            source_type=NPCSourceType.FUNCTIONARY,
            functionary=func,
            room=RoomProfileFactory(),
            assignment_role=AssignmentRole.GUARD,
            assigned_by=PersonaFactory(),
        )
        self.assertEqual(assignment.get_active_target(), func)

    def test_get_active_target_returns_npc_asset(self):
        from evennia_extensions.factories import RoomProfileFactory
        from world.assets.factories import NPCAssetFactory
        from world.scenes.factories import PersonaFactory

        asset = NPCAssetFactory()
        assignment = NPCAssignment.objects.create(
            source_type=NPCSourceType.NPC_ASSET,
            npc_asset=asset,
            room=RoomProfileFactory(),
            assignment_role=AssignmentRole.GUARD,
            assigned_by=PersonaFactory(),
        )
        self.assertEqual(assignment.get_active_target(), asset)

    def test_different_roles_same_room_ok(self):
        """A GUARD and a DOORMAN in the same room → both active, no collision."""
        from evennia_extensions.factories import RoomProfileFactory
        from world.npc_services.factories import FunctionaryFactory
        from world.scenes.factories import PersonaFactory

        room = RoomProfileFactory()
        persona = PersonaFactory()
        NPCAssignment.objects.create(
            source_type=NPCSourceType.FUNCTIONARY,
            functionary=FunctionaryFactory(room=room),
            room=room,
            assignment_role=AssignmentRole.GUARD,
            assigned_by=persona,
        )
        NPCAssignment.objects.create(
            source_type=NPCSourceType.FUNCTIONARY,
            functionary=FunctionaryFactory(room=room),
            room=room,
            assignment_role=AssignmentRole.DOORMAN,
            assigned_by=persona,
        )
