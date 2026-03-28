from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from world.events.models import Event
from world.roster.models import RosterEntry


class IsEventHostOrStaff(BasePermission):
    """Allow access to event hosts or staff."""

    def has_object_permission(self, request: Request, view: APIView, obj: Event) -> bool:
        if request.user.is_staff:
            return True
        active_entries = RosterEntry.objects.for_account(request.user)
        return obj.hosts.filter(
            persona__character__roster_entry__in=active_entries,
        ).exists()
