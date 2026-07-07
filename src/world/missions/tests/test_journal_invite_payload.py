"""Tests for the pending_invites + participant_count journal fields (#2049).

The journal payload now carries persona-scoped pending invites (so the web
can show incoming invites with accept/decline without a separate endpoint)
and a per-instance participant_count (driving solo-vs-group card routing).
"""

from django.test import TestCase

from world.missions.models import MissionInvite
from world.missions.services.journal import journal_for
from world.missions.services.run import invite_to_mission, share_mission, staff_assign_mission
from world.missions.tests.test_1036_group_play import _group_graph, _pc


def _holder_instance(name="jrn"):
    """An ACTIVE run with only the holder (no pre-shared p2)."""
    template, _entry, _opt_a, _opt_b, _dest_a, _dest_b = _group_graph(name)
    holder = _pc()
    instance = staff_assign_mission(template, holder)
    return instance, holder


class JournalInvitePayloadTest(TestCase):
    """The journal payload now carries pending invites + participant count."""

    def test_pending_invites_appear_on_journal(self):
        """A PENDING invite addressed to the invitee surfaces on their journal."""
        instance, holder = _holder_instance("pending")
        invitee = _pc()
        invite = invite_to_mission(
            instance,
            holder.sheet_data.primary_persona,
            invitee.sheet_data.primary_persona,
        )
        # The invitee is not yet a participant, so journal_for returns nothing
        # for them — but the invite is still PENDING. Once they accept and
        # become a participant, the invite appears on their journal entries.
        share_mission(instance, invitee)
        entries = journal_for(invitee)
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry.participant_count, 2)
        self.assertEqual(len(entry.pending_invites), 1)
        invite_row = entry.pending_invites[0]
        self.assertEqual(invite_row.invite_id, invite.pk)
        self.assertEqual(invite_row.instance_id, instance.pk)
        self.assertEqual(invite_row.template_name, instance.template.name)

    def test_no_pending_invites_is_empty_tuple(self):
        """A character with no invites sees an empty tuple."""
        _instance, holder = _holder_instance("solo")
        entries = journal_for(holder)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].pending_invites, ())
        self.assertEqual(entries[0].participant_count, 1)

    def test_participant_count_reflects_group(self):
        """A 2-participant instance reports participant_count == 2."""
        instance, holder = _holder_instance("group")
        p2 = _pc()
        share_mission(instance, p2)
        entries = journal_for(holder)
        self.assertEqual(entries[0].participant_count, 2)

    def test_declined_invite_does_not_surface(self):
        """A DECLINED invite is not PENDING, so it never appears."""
        instance, holder = _holder_instance("declined")
        invitee = _pc()
        invite = invite_to_mission(
            instance,
            holder.sheet_data.primary_persona,
            invitee.sheet_data.primary_persona,
        )
        share_mission(instance, invitee)
        invite.response = MissionInvite.Response.DECLINED
        invite.save(update_fields=["response"])
        entries = journal_for(invitee)
        self.assertEqual(entries[0].pending_invites, ())
