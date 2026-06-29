"""Event lifecycle + invitation RSVP actions (#1499).

Exposes the player-facing event verbs as real ``Action``s on the shared
``action.run()`` seam (ADR-0001) — converging the web ``EventViewSet`` and the
telnet ``CmdEvent`` on one path. All are REGISTRY backend, ``target_type=SELF``
(the actor acts on an event/invitation resolved by id). They wrap the existing
``world.events.services`` functions; no game logic lives here.

- ``CreateEventAction`` (key ``event_create``) — create a DRAFT event as host.
- ``ScheduleEventAction`` / ``StartEventAction`` / ``CompleteEventAction`` /
  ``CancelEventAction`` — host lifecycle transitions.
- ``InviteToEventAction`` (key ``event_invite``) — invite a persona/org/society.
- ``RespondInvitationAction`` (key ``respond_invitation``) — invitee RSVP.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ObjectDoesNotExist

from actions.base import Action
from actions.constants import ActionCategory
from actions.prerequisites import Prerequisite
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext
    from world.events.models import Event, EventInvitation
    from world.scenes.models import Persona


_MSG_NO_CHARACTER = "You must have an active character with a persona to manage events."
_MSG_WHICH_EVENT = "Which event? Provide an event id."
_MSG_WHICH_INVITATION = "Which invitation? Provide an invitation id."
_MSG_HOST_OR_STAFF_ONLY = "Only the event host or staff can do that."


@dataclass
class HasCharacterSheetPrerequisite(Prerequisite):
    """Actor must have a CharacterSheet (an active character)."""

    def is_met(
        self,
        actor: ObjectDB,
        target: ObjectDB | None = None,
        context: dict | None = None,
    ) -> tuple[bool, str]:
        try:
            actor.sheet_data  # noqa: B018
        except (AttributeError, ObjectDoesNotExist):
            return False, "No active character."
        return True, ""


def _actor_sheet(actor: ObjectDB) -> Any:
    try:
        return actor.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return None


def _actor_persona(actor: ObjectDB) -> Persona | None:
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    sheet = _actor_sheet(actor)
    if sheet is None:
        return None
    try:
        return active_persona_for_sheet(sheet)
    except ObjectDoesNotExist:
        return None


def _event_or_none(event_id: Any) -> Event | None:
    from world.events.models import Event  # noqa: PLC0415

    if event_id is None:
        return None
    try:
        return Event.objects.get(pk=int(event_id))
    except (Event.DoesNotExist, ValueError, TypeError):
        return None


def _invitation_or_none(invitation_id: Any) -> EventInvitation | None:
    from world.events.models import EventInvitation  # noqa: PLC0415

    if invitation_id is None:
        return None
    try:
        return EventInvitation.objects.select_related("event").get(pk=int(invitation_id))
    except (EventInvitation.DoesNotExist, ValueError, TypeError):
        return None


def _create_preflight_error(name: Any, location_id: Any, scheduled_real_time: Any) -> str | None:
    """Return the first input-validation error for ``CreateEventAction``, or None.

    Consolidates the name/location/time checks (one return each in the action
    body) so ``CreateEventAction.execute`` stays under ruff's return ceiling
    (PLR0911).
    """
    if not name:
        return "An event name is required."
    if location_id is None:
        return "An event location is required."
    if not isinstance(scheduled_real_time, datetime):
        return "A scheduled time is required."
    from django.utils import timezone  # noqa: PLC0415

    if scheduled_real_time <= timezone.now():
        return "Scheduled time must be in the future."
    return None


def _is_host(account: Any, event: Event) -> bool:
    """True if *account* owns an active persona that hosts *event*.

    Mirrors ``IsEventHostOrStaff``'s host check: an account is a host when one
    of its active roster entries backs a host persona of the event.
    """
    from world.roster.models import RosterEntry  # noqa: PLC0415

    active_entries = RosterEntry.objects.for_account(account)
    return event.hosts.filter(
        persona__character_sheet__roster_entry__in=active_entries,
    ).exists()


def _is_host_or_gm(account: Any, event: Event) -> bool:
    """True if *account* is a host, a scene GM of the event, or staff.

    Mirrors ``IsEventHostGMOrStaff``: staff short-circuits, then host, then an
    active-scene GM participation on the event's scene. All three are
    account-based (a staffer or GM can manage an event with no character).
    """
    if account.is_staff:
        return True
    if _is_host(account, event):
        return True
    from world.scenes.models import Scene  # noqa: PLC0415

    return Scene.objects.filter(
        event=event,
        is_active=True,
        participations__account=account,
        participations__is_gm=True,
    ).exists()


def _is_staff(account: Any) -> bool:
    return account.is_staff


@dataclass
class CreateEventAction(Action):
    """Create a DRAFT event with the actor's active persona as primary host."""

    key: str = "event_create"
    name: str = "Create Event"
    icon: str = "calendar-plus"
    category: str = "events"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [HasCharacterSheetPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.events.services import create_event  # noqa: PLC0415
        from world.events.types import EventError  # noqa: PLC0415
        from world.game_clock.constants import TimePhase  # noqa: PLC0415

        persona = _actor_persona(actor)
        if persona is None:
            return ActionResult(success=False, message=_MSG_NO_CHARACTER)

        name = kwargs.get("name")
        location_id = kwargs.get("location_id")
        scheduled_real_time = kwargs.get("scheduled_real_time")
        err = _create_preflight_error(name, location_id, scheduled_real_time)
        if err:
            return ActionResult(success=False, message=err)

        try:
            event = create_event(
                name=name,
                description=kwargs.get("description", "") or "",
                location_id=int(location_id),
                scheduled_real_time=scheduled_real_time,
                host_persona=persona,
                is_public=kwargs.get("is_public", True),
                scheduled_ic_time=kwargs.get("scheduled_ic_time"),
                time_phase=kwargs.get("time_phase", TimePhase.DAY),
            )
        except EventError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=f"You create the event '{event.name}' (#{event.pk}, draft).",
            data={"event_id": event.pk},
        )


class _HostLifecycleAction(Action):
    """Base for account-authorized host event-lifecycle transitions.

    These transitions (schedule/start/complete/cancel) are **account-authorized**:
    a staffer or scene GM can manage an event they do not own, with no character
    involved, so they take an ``account`` kwarg (not an actor) and carry no
    character-sheet prerequisite. The host/GM/staff gate is the same account-
    based predicate as the DRF permission classes (``IsEventHostOrStaff`` /
    ``IsEventHostGMOrStaff``); the viewset passes ``actor=None`` through
    ``action.run()``. Field-free (only shares the no-op prerequisite gate).
    """

    def get_prerequisites(self) -> list[Prerequisite]:
        return []


@dataclass
class ScheduleEventAction(_HostLifecycleAction):
    """Transition an event from DRAFT to SCHEDULED (host/staff)."""

    key: str = "event_schedule"
    name: str = "Schedule Event"
    icon: str = "calendar-clock"
    category: str = "events"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB | None,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.events.services import schedule_event  # noqa: PLC0415
        from world.events.types import EventError  # noqa: PLC0415

        account = kwargs.get("account")
        event = _event_or_none(kwargs.get("event_id"))
        if event is None:
            return ActionResult(success=False, message=_MSG_WHICH_EVENT)
        if account is None or not (_is_host(account, event) or _is_staff(account)):
            return ActionResult(success=False, message=_MSG_HOST_OR_STAFF_ONLY)
        try:
            schedule_event(event)
        except EventError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=f"'{event.name}' is now scheduled.",
            data={"event_id": event.pk},
        )


@dataclass
class StartEventAction(_HostLifecycleAction):
    """Transition an event from SCHEDULED to ACTIVE, spawning its Scene."""

    key: str = "event_start"
    name: str = "Start Event"
    icon: str = "play"
    category: str = "events"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB | None,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.events.services import start_event  # noqa: PLC0415
        from world.events.types import EventError  # noqa: PLC0415

        account = kwargs.get("account")
        event = _event_or_none(kwargs.get("event_id"))
        if event is None:
            return ActionResult(success=False, message=_MSG_WHICH_EVENT)
        if account is None or not (_is_host(account, event) or _is_staff(account)):
            return ActionResult(success=False, message=_MSG_HOST_OR_STAFF_ONLY)
        try:
            start_event(event)
        except EventError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=f"'{event.name}' has started.",
            data={"event_id": event.pk},
        )


@dataclass
class CompleteEventAction(_HostLifecycleAction):
    """Transition an event from ACTIVE to COMPLETED (host, scene GM, or staff)."""

    key: str = "event_complete"
    name: str = "Complete Event"
    icon: str = "check-check"
    category: str = "events"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB | None,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.events.services import complete_event  # noqa: PLC0415
        from world.events.types import EventError  # noqa: PLC0415

        account = kwargs.get("account")
        event = _event_or_none(kwargs.get("event_id"))
        if event is None:
            return ActionResult(success=False, message=_MSG_WHICH_EVENT)
        if account is None or not (_is_host_or_gm(account, event) or _is_staff(account)):
            return ActionResult(
                success=False,
                message="Only the host, a scene GM, or staff can do that.",
            )
        try:
            complete_event(event)
        except EventError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=f"'{event.name}' is complete.",
            data={"event_id": event.pk},
        )


@dataclass
class CancelEventAction(_HostLifecycleAction):
    """Cancel a DRAFT or SCHEDULED event (host/staff only — not GMs)."""

    key: str = "event_cancel"
    name: str = "Cancel Event"
    icon: str = "calendar-x"
    category: str = "events"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB | None,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.events.services import cancel_event  # noqa: PLC0415
        from world.events.types import EventError  # noqa: PLC0415

        account = kwargs.get("account")
        event = _event_or_none(kwargs.get("event_id"))
        if event is None:
            return ActionResult(success=False, message=_MSG_WHICH_EVENT)
        if account is None or not (_is_host(account, event) or _is_staff(account)):
            return ActionResult(success=False, message=_MSG_HOST_OR_STAFF_ONLY)
        try:
            cancel_event(event)
        except EventError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=f"'{event.name}' has been cancelled.",
            data={"event_id": event.pk},
        )


@dataclass
class InviteToEventAction(Action):
    """Invite a persona, organization, or society to an event (host/staff).

    Account-authorized (a staffer can invite without a character); takes an
    ``account`` kwarg and passes ``actor=None`` through ``action.run()``.
    """

    key: str = "event_invite"
    name: str = "Invite to Event"
    icon: str = "user-plus"
    category: str = "events"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return []

    def execute(
        self,
        actor: ObjectDB | None,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from django.db import IntegrityError  # noqa: PLC0415
        from django.shortcuts import get_object_or_404  # noqa: PLC0415

        from world.events.constants import InvitationTargetType  # noqa: PLC0415
        from world.events.services import (  # noqa: PLC0415
            invite_organization,
            invite_persona,
            invite_society,
        )
        from world.events.types import EventError  # noqa: PLC0415
        from world.scenes.models import Persona  # noqa: PLC0415
        from world.societies.models import Organization, Society  # noqa: PLC0415

        account = kwargs.get("account")
        event = _event_or_none(kwargs.get("event_id"))
        if event is None:
            return ActionResult(success=False, message=_MSG_WHICH_EVENT)
        if account is None or not (_is_host(account, event) or _is_staff(account)):
            return ActionResult(success=False, message="Only the event host or staff can invite.")
        target_type = kwargs.get("target_type")
        target_id = kwargs.get("target_id")
        target_model = (
            {
                InvitationTargetType.PERSONA: Persona,
                InvitationTargetType.ORGANIZATION: Organization,
                InvitationTargetType.SOCIETY: Society,
            }.get(target_type)
            if target_id is not None
            else None
        )
        if target_model is None:
            return ActionResult(
                success=False,
                message="An invitation target is required (persona=, org=, or society=).",
            )
        target = get_object_or_404(target_model, pk=target_id)

        invited_by_id = kwargs.get("invited_by_persona_id")
        invited_by = None
        if invited_by_id is not None:
            invited_by = Persona.objects.filter(pk=invited_by_id).first()

        invite_fn = {
            InvitationTargetType.PERSONA: invite_persona,
            InvitationTargetType.ORGANIZATION: invite_organization,
            InvitationTargetType.SOCIETY: invite_society,
        }[target_type]
        try:
            invitation = invite_fn(event, target, invited_by=invited_by)
        except IntegrityError:
            return ActionResult(success=False, message=EventError.INVITE_DUPLICATE)
        target_name = target.name if hasattr(target, "name") else f"#{target.pk}"
        return ActionResult(
            success=True,
            message=f"You invite {target_name} to '{event.name}'.",
            data={"invitation_id": invitation.pk},
        )


@dataclass
class RespondInvitationAction(Action):
    """An invitee RSVPs accept/decline to their own persona invitation."""

    key: str = "respond_invitation"
    name: str = "RSVP"
    icon: str = "calendar-check"
    category: str = "events"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [HasCharacterSheetPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.events.constants import InvitationResponse  # noqa: PLC0415
        from world.events.services import respond_to_invitation  # noqa: PLC0415
        from world.events.types import EventError  # noqa: PLC0415

        persona = _actor_persona(actor)
        if persona is None:
            return ActionResult(success=False, message=_MSG_NO_CHARACTER)
        invitation = _invitation_or_none(kwargs.get("invitation_id"))
        if invitation is None:
            return ActionResult(success=False, message=_MSG_WHICH_INVITATION)

        response = kwargs.get("response")
        if response not in InvitationResponse.values:
            return ActionResult(success=False, message="RSVP must be 'accept' or 'decline'.")
        try:
            respond_to_invitation(invitation, persona, response=response)
        except EventError as exc:
            return ActionResult(success=False, message=exc.user_message)

        verb = "accept" if response == InvitationResponse.ACCEPTED else "decline"
        return ActionResult(
            success=True,
            message=f"You {verb} the invitation to '{invitation.event.name}'.",
            data={"invitation_id": invitation.pk, "response": response},
        )


# Module-level singletons — registered in actions/registry.py
event_create = CreateEventAction()
event_schedule = ScheduleEventAction()
event_start = StartEventAction()
event_complete = CompleteEventAction()
event_cancel = CancelEventAction()
event_invite = InviteToEventAction()
respond_invitation = RespondInvitationAction()
