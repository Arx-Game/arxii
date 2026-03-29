from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from world.events.models import Event
from world.roster.models import RosterEntry
from world.scenes.models import Scene


class IsEventHostOrStaff(BasePermission):
    """Allow access to event hosts or staff."""

    def has_object_permission(self, request: Request, view: APIView, obj: Event) -> bool:
        if request.user.is_staff:
            return True
        active_entries = RosterEntry.objects.for_account(request.user)
        return obj.hosts.filter(
            persona__character__roster_entry__in=active_entries,
        ).exists()


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
