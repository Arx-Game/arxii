"""Tests for the mission invite + respond services (#887)."""

from django.test import TestCase

from world.missions.models import MissionInvite, MissionParticipant
from world.missions.services.run import (
    InviteError,
    invite_to_mission,
    respond_to_mission_invite,
    staff_assign_mission,
)
from world.missions.tests.test_1036_group_play import _group_graph, _pc


def _holder_instance(name="svc"):
    """An ACTIVE run with only the holder (no pre-shared p2)."""
    template, _entry, _opt_a, _opt_b, _dest_a, _dest_b = _group_graph(name)
    holder = _pc()
    instance = staff_assign_mission(template, holder)
    return instance, holder


class InviteToMissionTest(TestCase):
    def test_holder_invites_creates_pending_invite(self) -> None:
        instance, holder = _holder_instance("ok")
        invitee = _pc()
        invitee_persona = invitee.sheet_data.primary_persona
        holder_persona = holder.sheet_data.primary_persona
        invite = invite_to_mission(instance, holder_persona, invitee_persona)
        self.assertEqual(invite.response, MissionInvite.Response.PENDING)
        self.assertEqual(invite.target_persona, invitee_persona)
        self.assertEqual(invite.invited_by, holder_persona)

    def test_non_holder_cannot_invite(self) -> None:
        instance, _holder = _holder_instance("noholder")
        non_holder = _pc()
        # non_holder tries to invite someone — but they aren't the contract holder.
        invitee = _pc()
        with self.assertRaises(InviteError):
            invite_to_mission(
                instance,
                non_holder.sheet_data.primary_persona,
                invitee.sheet_data.primary_persona,
            )

    def test_cannot_invite_existing_participant(self) -> None:
        instance, holder = _holder_instance("dup")
        invitee = _pc()
        from world.missions.services.run import share_mission

        share_mission(instance, invitee)  # now a participant
        with self.assertRaises(InviteError):
            invite_to_mission(
                instance,
                holder.sheet_data.primary_persona,
                invitee.sheet_data.primary_persona,
            )


class RespondToMissionInviteTest(TestCase):
    def _make_invite(self, name="rsvp"):
        instance, holder = _holder_instance(name)
        invitee = _pc()
        invite = invite_to_mission(
            instance,
            holder.sheet_data.primary_persona,
            invitee.sheet_data.primary_persona,
        )
        return invite, instance, invitee

    def test_accept_adds_participant(self) -> None:
        invite, _instance, invitee = self._make_invite()
        participant = respond_to_mission_invite(invite, MissionInvite.Response.ACCEPTED)
        self.assertEqual(participant.character, invitee)
        self.assertFalse(participant.is_contract_holder)
        invite.refresh_from_db()
        self.assertEqual(invite.response, MissionInvite.Response.ACCEPTED)
        self.assertIsNotNone(invite.responded_at)

    def test_decline_does_not_add_participant(self) -> None:
        invite, instance, invitee = self._make_invite("decline")
        result = respond_to_mission_invite(invite, MissionInvite.Response.DECLINED)
        self.assertIsNone(result)
        self.assertFalse(
            MissionParticipant.objects.filter(instance=instance, character=invitee).exists()
        )
        invite.refresh_from_db()
        self.assertEqual(invite.response, MissionInvite.Response.DECLINED)

    def test_cannot_respond_twice(self) -> None:
        invite, _instance, _invitee = self._make_invite("twice")
        respond_to_mission_invite(invite, MissionInvite.Response.ACCEPTED)
        with self.assertRaises(InviteError):
            respond_to_mission_invite(invite, MissionInvite.Response.DECLINED)
