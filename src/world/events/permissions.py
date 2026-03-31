from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from world.events.models import Event, EventInvitation
from world.roster.models import RosterEntry
from world.scenes.models import Scene


def _is_event_host_or_staff(request: Request, event: Event) -> bool:
    """Check if the requesting user is a host of the event or staff."""
    if request.user.is_staff:
        return True
    active_entries = RosterEntry.objects.for_account(request.user)
    return event.hosts.filter(
        persona__character__roster_entry__in=active_entries,
    ).exists()


class IsEventHostOrStaff(BasePermission):
    """Allow access to event hosts or staff."""

    def has_object_permission(self, request: Request, view: APIView, obj: Event) -> bool:
        return _is_event_host_or_staff(request, obj)


class IsInvitationEventHostOrStaff(BasePermission):
    """Allow access to hosts of the invitation's parent event, or staff."""

    def has_object_permission(self, request: Request, view: APIView, obj: EventInvitation) -> bool:
        return _is_event_host_or_staff(request, obj.event)


class IsEventHostGMOrStaff(BasePermission):
    """Allow access to event hosts, scene GMs, or staff.

    Extends host check with GM check: if the event has an active scene and
    the requesting user is a GM in that scene, permission is granted.
    """

    def has_object_permission(self, request: Request, view: APIView, obj: Event) -> bool:
        if request.user.is_staff:
            return True
        active_entries = RosterEntry.objects.for_account(request.user)
        if obj.hosts.filter(
            persona__character__roster_entry__in=active_entries,
        ).exists():
            return True
        # Check if user is a GM in the event's active scene
        return Scene.objects.filter(
            event=obj,
            is_active=True,
            participations__account=request.user,
            participations__is_gm=True,
        ).exists()
