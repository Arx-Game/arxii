from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from world.events.models import Event


class IsEventHostOrStaff(BasePermission):
    """Allow access to event hosts or staff."""

    def has_object_permission(self, request: Request, view: APIView, obj: Event) -> bool:
        if request.user.is_staff:
            return True
        return obj.hosts.filter(
            persona__character__roster_entry__tenures__player_data__account=request.user,
            persona__character__roster_entry__tenures__end_date__isnull=True,
        ).exists()
