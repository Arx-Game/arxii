"""Telnet journey tests for CmdEvent — event lifecycle + invitee RSVP (#1499).

Drives ``CmdEvent.func()`` end-to-end with real characters through
``action.run()`` (the same REGISTRY seam the web ``EventViewSet`` /
``EventInvitationViewSet`` use), asserting the DB-state outcome of each verb
rather than mocking. Proves the telnet command reaches each already-built
event Action:

  - ``event create name=… room=… when=…`` → DRAFT Event with the caller's
    active persona as the primary host.
  - ``event schedule <id>`` / ``start <id>`` / ``complete <id>`` / ``cancel <id>``
    → the host-lifecycle transitions (DRAFT→SCHEDULED→ACTIVE→COMPLETED,
    DRAFT/SCHEDULED→CANCELLED).
  - ``event invite <id> persona=<name>`` → a PENDING persona EventInvitation.
  - ``event rsvp <id> accept|decline`` → the invitee's InvitationResponse flips
    ACCEPTED / DECLINED (the invitee acts as their own active persona).

The host lifecycle + invite verbs are **account-authorized**: the host's
account must own an active roster tenure backing the host persona's character
sheet, so ``_is_host(account, event)`` resolves. ``create`` and ``rsvp`` act
*as* a persona (the caller's resolved character is the actor). ObjectDB rows
live in ``setUp`` with ``idmapper.flush_cache()`` to avoid idmapper
contamination between tests — mirroring ``test_duel_command_journey.py``.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock

from django.test import TestCase
from django.utils import timezone
from evennia.utils import idmapper

from commands.events import CmdEvent
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.events.constants import EventStatus, InvitationResponse
from world.events.models import Event, EventInvitation
from world.events.services import create_event
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)


def _make_room(name: str = "Feast Hall") -> Any:
    """A room with a RoomProfile (events anchor on the profile, not ObjectDB)."""
    room = ObjectDBFactory(db_key=name, db_typeclass_path="typeclasses.rooms.Room")
    # Room.at_object_creation auto-creates a RoomProfile; resolve it so the
    # command's room-by-name lookup finds a profile-backed room.
    from evennia_extensions.models import RoomProfile

    RoomProfile.objects.get_or_create(objectdb=room)
    return room


def _make_pc(name: str, room: Any) -> tuple[Any, Any]:
    """Return (character ObjectDB, CharacterSheet) with a PRIMARY persona.

    The sheet's auto-created PRIMARY persona is what ``active_persona_for_sheet``
    resolves to, so ``create`` / ``rsvp`` act on it.
    """
    actor = CharacterFactory(db_key=name, location=room)
    sheet = CharacterSheetFactory(character=actor)
    return actor, sheet


def _attach_account(actor: Any, sheet: Any) -> Any:
    """Give a character an active roster tenure so host checks resolve.

    The host-lifecycle / invite verbs are account-authorized: ``_is_host``
    walks account → PlayerData → RosterTenure(end_date=None) → RosterEntry →
    the host persona's character sheet. Returns the account.
    """
    player_data = PlayerDataFactory()
    entry = RosterEntryFactory(character_sheet=sheet)
    RosterTenureFactory(player_data=player_data, roster_entry=entry)
    # ``caller.account`` is what the command reads for account-authorized verbs.
    actor.account = player_data.account
    return player_data.account


def _run(caller: Any, args: str) -> CmdEvent:
    """Construct and execute ``event <args>`` as *caller* would over telnet."""
    cmd = CmdEvent()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"event {args}".strip()
    cmd.cmdname = "event"
    cmd.func()
    return cmd


def _when(days: int = 7) -> str:
    """A future ``when=`` value in the ``YYYY-MM-DD HH:MM`` telnet form.

    ``days`` is kept distinct per test so ``validate_location_gap`` (a 6-hour
    window) doesn't reject a create for colliding with another event at the
    same room.
    """
    future = timezone.now() + timedelta(days=days)
    return future.strftime("%Y-%m-%d %H:%M")


class CmdEventJourneyTests(TestCase):
    def setUp(self) -> None:
        idmapper.models.flush_cache()
        self.room = _make_room()
        # Host: character + sheet + PRIMARY persona + active account/tenure.
        self.host, self.host_sheet = _make_pc("Host", self.room)
        self.host_account = _attach_account(self.host, self.host_sheet)
        self.host.msg = MagicMock()
        # Invitee: character + sheet + PRIMARY persona (rsvp acts as this persona).
        self.invitee, self.invitee_sheet = _make_pc("Invitee", self.room)
        self.invitee.msg = MagicMock()
        # Seed an event owned by the host persona (the create verb is tested
        # separately; lifecycle/invite/rsvp drive a known-good event).
        self.event = create_event(
            name="The Grand Gala",
            location_id=self._room_profile_id(self.room),
            scheduled_real_time=timezone.now() + timedelta(days=7),
            host_persona=self.host_sheet.primary_persona,
        )

    @staticmethod
    def _room_profile_id(room: Any) -> int:
        from evennia_extensions.models import RoomProfile

        return RoomProfile.objects.get(objectdb=room).pk

    # -- create ---------------------------------------------------------------

    def test_create_makes_draft_event_with_host(self) -> None:
        # A fresh room + a distinct day offset so validate_location_gap doesn't
        # reject this create for colliding with the setUp-seeded gala.
        room = _make_room("Garden")
        self.host.location = room
        cmd = _run(
            self.host,
            f"create name=Salon room=Garden when={_when(days=10)} desc=A soirée",
        )
        event = Event.objects.filter(name="Salon").first()
        if event is None:
            msgs = "\n".join(str(c.args[0]) for c in self.host.msg.call_args_list if c.args)
            self.fail(
                f"event create made no event. Messages:\n{msgs}\n(raw_string={cmd.raw_string})"
            )
        self.assertIsNotNone(event, "event create should make a DRAFT Event")
        self.assertEqual(event.status, EventStatus.DRAFT)
        self.assertTrue(
            event.hosts.filter(persona=self.host_sheet.primary_persona, is_primary=True).exists(),
            "the caller's active persona should be the primary host",
        )

    # -- host lifecycle -------------------------------------------------------

    def test_schedule_transitions_draft_to_scheduled(self) -> None:
        _run(self.host, f"schedule {self.event.pk}")
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, EventStatus.SCHEDULED)

    def test_start_transitions_scheduled_to_active(self) -> None:
        _run(self.host, f"schedule {self.event.pk}")
        _run(self.host, f"start {self.event.pk}")
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, EventStatus.ACTIVE)

    def test_complete_transitions_active_to_completed(self) -> None:
        _run(self.host, f"schedule {self.event.pk}")
        _run(self.host, f"start {self.event.pk}")
        _run(self.host, f"complete {self.event.pk}")
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, EventStatus.COMPLETED)

    def test_cancel_transitions_draft_to_cancelled(self) -> None:
        _run(self.host, f"cancel {self.event.pk}")
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, EventStatus.CANCELLED)

    def test_non_host_cannot_schedule(self) -> None:
        """An account with no tenure on the host persona is rejected (no state change)."""
        _run(self.invitee, f"schedule {self.event.pk}")
        self.event.refresh_from_db()
        self.assertEqual(
            self.event.status, EventStatus.DRAFT, "non-host must not transition the event"
        )

    # -- invite ---------------------------------------------------------------

    def test_invite_creates_pending_persona_invitation(self) -> None:
        _run(self.host, f"invite {self.event.pk} persona=Invitee")
        invitation = EventInvitation.objects.filter(
            event=self.event,
            target_persona=self.invitee_sheet.primary_persona,
        ).first()
        self.assertIsNotNone(invitation, "event invite persona= should make an invitation")
        self.assertEqual(invitation.response, InvitationResponse.PENDING)

    # -- rsvp -----------------------------------------------------------------

    def test_rsvp_accept_flips_invitation_to_accepted(self) -> None:
        _run(self.host, f"invite {self.event.pk} persona=Invitee")
        invitation = EventInvitation.objects.get(
            event=self.event, target_persona=self.invitee_sheet.primary_persona
        )
        _run(self.invitee, f"rsvp {invitation.pk} accept")
        invitation.refresh_from_db()
        self.assertEqual(invitation.response, InvitationResponse.ACCEPTED)

    def test_rsvp_decline_flips_invitation_to_declined(self) -> None:
        _run(self.host, f"invite {self.event.pk} persona=Invitee")
        invitation = EventInvitation.objects.get(
            event=self.event, target_persona=self.invitee_sheet.primary_persona
        )
        _run(self.invitee, f"rsvp {invitation.pk} decline")
        invitation.refresh_from_db()
        self.assertEqual(invitation.response, InvitationResponse.DECLINED)

    def test_rsvp_by_non_target_is_rejected(self) -> None:
        """A persona that is not the invitation's target may not RSVP to it."""
        _run(self.host, f"invite {self.event.pk} persona=Invitee")
        invitation = EventInvitation.objects.get(
            event=self.event, target_persona=self.invitee_sheet.primary_persona
        )
        # The host is not the invitee — rsvp must not flip the response.
        _run(self.host, f"rsvp {invitation.pk} accept")
        invitation.refresh_from_db()
        self.assertEqual(invitation.response, InvitationResponse.PENDING)
