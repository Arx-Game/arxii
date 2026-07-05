"""Tests for the MissionInvite RSVP model (#887)."""

from django.db import IntegrityError
from django.test import TestCase

from world.missions.models import MissionInvite
from world.missions.services.run import staff_assign_mission
from world.missions.tests.test_1036_group_play import _group_graph, _pc


def _holder_instance(name="invite"):
    """An ACTIVE run with only the holder (no pre-shared p2)."""
    template, _entry, _opt_a, _opt_b, _dest_a, _dest_b = _group_graph(name)
    holder = _pc()
    instance = staff_assign_mission(template, holder)
    return instance, holder


class MissionInviteModelTest(TestCase):
    def test_create_pending_invite(self) -> None:
        instance, holder = _holder_instance()
        invitee = _pc()
        invitee_persona = invitee.sheet_data.primary_persona
        holder_persona = holder.sheet_data.primary_persona
        invite = MissionInvite.objects.create(
            instance=instance,
            target_persona=invitee_persona,
            invited_by=holder_persona,
        )
        self.assertEqual(invite.response, MissionInvite.Response.PENDING)
        self.assertIsNone(invite.responded_at)
        self.assertEqual(invite.target_persona, invitee_persona)
        self.assertEqual(invite.invited_by, holder_persona)

    def test_unique_instance_target_persona(self) -> None:
        instance, holder = _holder_instance("uniq")
        invitee = _pc()
        invitee_persona = invitee.sheet_data.primary_persona
        holder_persona = holder.sheet_data.primary_persona
        MissionInvite.objects.create(
            instance=instance,
            target_persona=invitee_persona,
            invited_by=holder_persona,
        )
        with self.assertRaises(IntegrityError):
            MissionInvite.objects.create(
                instance=instance,
                target_persona=invitee_persona,
                invited_by=holder_persona,
            )

    def test_response_choices_default_and_string(self) -> None:
        instance, holder = _holder_instance("str")
        invitee = _pc()
        invite = MissionInvite.objects.create(
            instance=instance,
            target_persona=invitee.sheet_data.primary_persona,
            invited_by=holder.sheet_data.primary_persona,
        )
        self.assertIn("pending", str(invite).lower())
