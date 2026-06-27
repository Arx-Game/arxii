"""Unit tests for the event Actions (#1499).

Focused coverage of the authorization + status paths the telnet/web E2E
touches only lightly:

  - ``ScheduleEventAction`` / ``InviteToEventAction`` reject a non-host account.
  - ``ScheduleEventAction`` rejects a non-staff non-host even when the event is
    theirs to *read* (public events are visible to all, but only the host /
    scene GM / staff may transition them).
  - ``CompleteEventAction`` admits a scene GM (the host-GM-or-staff gate).
  - ``RespondInvitationAction`` rejects an RSVP on an ACTIVE event (RSVP_CLOSED),
    on an org (non-persona) invitation (RSVP_NOT_PERSONA), and by a persona that
    is not the invitation's target (RSVP_NOT_YOURS).

The actions wrap ``world.events.services``; these tests assert the
``ActionResult`` outcome (success/message) and the resulting DB state rather
than mocking. ``CharacterFactory`` builds Evennia ObjectDB rows (not
deepcopy-safe), so ``setUp`` (not ``setUpTestData``) is used — mirroring
``test_duel_actions.py``.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import django.test
from django.utils import timezone

from actions.definitions.events import (
    CompleteEventAction,
    InviteToEventAction,
    RespondInvitationAction,
    ScheduleEventAction,
)
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.events.constants import (
    EventStatus,
    InvitationResponse,
    InvitationTargetType,
)
from world.events.factories import (
    EventInvitationFactory,
)
from world.events.services import create_event, start_event
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)
from world.scenes.factories import SceneGMParticipationFactory
from world.scenes.models import Scene
from world.societies.factories import OrganizationFactory


def _make_room(name: str = "TestRoom") -> Any:
    return ObjectDBFactory(db_key=name, db_typeclass_path="typeclasses.rooms.Room")


def _make_pc(name: str, room: Any) -> tuple[Any, Any]:
    """Return (character ObjectDB, CharacterSheet) with a PRIMARY persona."""
    actor = CharacterFactory(db_key=name, location=room)
    sheet = CharacterSheetFactory(character=actor)
    return actor, sheet


def _account_for(sheet: Any) -> Any:
    """An account that owns an active tenure on *sheet* (the host account)."""
    player_data = PlayerDataFactory()
    entry = RosterEntryFactory(character_sheet=sheet)
    RosterTenureFactory(player_data=player_data, roster_entry=entry)
    return player_data.account


class ScheduleEventActionTests(django.test.TestCase):
    def setUp(self) -> None:
        self.room = _make_room()
        self.host, self.host_sheet = _make_pc("Host", self.room)
        self.host_account = _account_for(self.host_sheet)
        self.event = create_event(
            name="Gala",
            location_id=self._room_profile_id(self.room),
            scheduled_real_time=timezone.now() + timedelta(days=7),
            host_persona=self.host_sheet.primary_persona,
        )

    @staticmethod
    def _room_profile_id(room: Any) -> int:
        from evennia_extensions.models import RoomProfile

        return RoomProfile.objects.get(objectdb=room).pk

    def test_host_can_schedule(self) -> None:
        result = ScheduleEventAction().run(
            actor=None, account=self.host_account, event_id=self.event.pk
        )
        self.assertTrue(result.success)
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, EventStatus.SCHEDULED)

    def test_non_host_account_rejected(self) -> None:
        other_account = AccountFactory()
        result = ScheduleEventAction().run(
            actor=None, account=other_account, event_id=self.event.pk
        )
        self.assertFalse(result.success)
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, EventStatus.DRAFT, "non-host must not transition")

    def test_missing_event_id_rejected(self) -> None:
        result = ScheduleEventAction().run(actor=None, account=self.host_account, event_id=999999)
        self.assertFalse(result.success)

    def test_staff_can_schedule_any_event(self) -> None:
        staff_account = AccountFactory(is_staff=True)
        result = ScheduleEventAction().run(
            actor=None, account=staff_account, event_id=self.event.pk
        )
        self.assertTrue(result.success)


class CompleteEventActionTests(django.test.TestCase):
    def setUp(self) -> None:
        self.room = _make_room()
        self.host, self.host_sheet = _make_pc("Host", self.room)
        self.host_account = _account_for(self.host_sheet)
        self.event = create_event(
            name="Gala",
            location_id=self._room_profile_id(self.room),
            scheduled_real_time=timezone.now() + timedelta(days=7),
            host_persona=self.host_sheet.primary_persona,
        )
        # Bring it to ACTIVE so complete is a legal transition.
        from world.events.services import schedule_event

        schedule_event(self.event)
        start_event(self.event)

    @staticmethod
    def _room_profile_id(room: Any) -> int:
        from evennia_extensions.models import RoomProfile

        return RoomProfile.objects.get(objectdb=room).pk

    def test_scene_gm_can_complete(self) -> None:
        """A scene GM on the event's active scene may complete it (host-GM-or-staff gate)."""
        gm_account = AccountFactory()
        scene = Scene.objects.filter(event=self.event, is_active=True).first()
        self.assertIsNotNone(scene, "start_event should spawn the event's scene")
        SceneGMParticipationFactory(scene=scene, account=gm_account)
        result = CompleteEventAction().run(actor=None, account=gm_account, event_id=self.event.pk)
        self.assertTrue(result.success)
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, EventStatus.COMPLETED)

    def test_non_host_non_gm_rejected(self) -> None:
        other_account = AccountFactory()
        result = CompleteEventAction().run(
            actor=None, account=other_account, event_id=self.event.pk
        )
        self.assertFalse(result.success)
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, EventStatus.ACTIVE)


class InviteToEventActionTests(django.test.TestCase):
    def setUp(self) -> None:
        self.room = _make_room()
        self.host, self.host_sheet = _make_pc("Host", self.room)
        self.host_account = _account_for(self.host_sheet)
        self.event = create_event(
            name="Gala",
            location_id=self._room_profile_id(self.room),
            scheduled_real_time=timezone.now() + timedelta(days=7),
            host_persona=self.host_sheet.primary_persona,
        )
        self.target_persona = CharacterSheetFactory().primary_persona

    @staticmethod
    def _room_profile_id(room: Any) -> int:
        from evennia_extensions.models import RoomProfile

        return RoomProfile.objects.get(objectdb=room).pk

    def test_host_can_invite_persona(self) -> None:
        result = InviteToEventAction().run(
            actor=None,
            account=self.host_account,
            event_id=self.event.pk,
            target_type=InvitationTargetType.PERSONA,
            target_id=self.target_persona.pk,
        )
        self.assertTrue(result.success)

    def test_non_host_rejected(self) -> None:
        other_account = AccountFactory()
        result = InviteToEventAction().run(
            actor=None,
            account=other_account,
            event_id=self.event.pk,
            target_type=InvitationTargetType.PERSONA,
            target_id=self.target_persona.pk,
        )
        self.assertFalse(result.success)

    def test_duplicate_invite_returns_failure(self) -> None:
        EventInvitationFactory(
            event=self.event,
            target_type=InvitationTargetType.PERSONA,
            target_persona=self.target_persona,
        )
        result = InviteToEventAction().run(
            actor=None,
            account=self.host_account,
            event_id=self.event.pk,
            target_type=InvitationTargetType.PERSONA,
            target_id=self.target_persona.pk,
        )
        self.assertFalse(result.success)


class RespondInvitationActionTests(django.test.TestCase):
    def setUp(self) -> None:
        self.room = _make_room()
        self.host, self.host_sheet = _make_pc("Host", self.room)
        self.event = create_event(
            name="Gala",
            location_id=self._room_profile_id(self.room),
            scheduled_real_time=timezone.now() + timedelta(days=7),
            host_persona=self.host_sheet.primary_persona,
        )
        # The invitee: their own character/sheet with a PRIMARY persona.
        self.invitee, self.invitee_sheet = _make_pc("Invitee", self.room)
        self.invitee_persona = self.invitee_sheet.primary_persona

    @staticmethod
    def _room_profile_id(room: Any) -> int:
        from evennia_extensions.models import RoomProfile

        return RoomProfile.objects.get(objectdb=room).pk

    def _invitation(self, **overrides: Any) -> Any:
        defaults = {
            "event": self.event,
            "target_type": InvitationTargetType.PERSONA,
            "target_persona": self.invitee_persona,
        }
        defaults.update(overrides)
        return EventInvitationFactory(**defaults)

    def test_accept_flips_to_accepted(self) -> None:
        invitation = self._invitation()
        result = RespondInvitationAction().run(
            actor=self.invitee, invitation_id=invitation.pk, response=InvitationResponse.ACCEPTED
        )
        self.assertTrue(result.success)
        invitation.refresh_from_db()
        self.assertEqual(invitation.response, InvitationResponse.ACCEPTED)

    def test_wrong_persona_rejected(self) -> None:
        """A persona that is not the invitation's target may not RSVP (RSVP_NOT_YOURS)."""
        invitation = self._invitation(target_persona=self.invitee_persona)
        # The host is not the invitee.
        result = RespondInvitationAction().run(
            actor=self.host, invitation_id=invitation.pk, response=InvitationResponse.ACCEPTED
        )
        self.assertFalse(result.success)
        invitation.refresh_from_db()
        self.assertEqual(invitation.response, InvitationResponse.PENDING)

    def test_rsvp_on_active_event_rejected(self) -> None:
        """RSVP closes once the event is ACTIVE (RSVP_CLOSED)."""
        invitation = self._invitation()
        from world.events.services import schedule_event

        schedule_event(self.event)
        start_event(self.event)
        result = RespondInvitationAction().run(
            actor=self.invitee, invitation_id=invitation.pk, response=InvitationResponse.ACCEPTED
        )
        self.assertFalse(result.success)
        invitation.refresh_from_db()
        self.assertEqual(invitation.response, InvitationResponse.PENDING)

    def test_rsvp_on_org_invitation_rejected(self) -> None:
        """Only persona invitations can be RSVP'd (RSVP_NOT_PERSONA)."""
        org = OrganizationFactory()
        invitation = self._invitation(
            target_type=InvitationTargetType.ORGANIZATION,
            target_persona=None,
            target_organization=org,
        )
        result = RespondInvitationAction().run(
            actor=self.invitee, invitation_id=invitation.pk, response=InvitationResponse.ACCEPTED
        )
        self.assertFalse(result.success)

    def test_missing_invitation_rejected(self) -> None:
        result = RespondInvitationAction().run(
            actor=self.invitee, invitation_id=999999, response=InvitationResponse.ACCEPTED
        )
        self.assertFalse(result.success)
