"""DRF permissions for the societies membership API (#1511)."""

from __future__ import annotations

from rest_framework import permissions
from rest_framework.request import Request

from world.societies.models import OrganizationMembership


class IsOwnMembership(permissions.BasePermission):
    """Permit action on a membership only if the user currently plays its sheet."""

    def has_object_permission(
        self,
        request: Request,
        view: object,
        obj: OrganizationMembership,
    ) -> bool:
        if request.user.is_staff:
            return True
        return OrganizationMembership.objects.filter(
            pk=obj.pk,
            persona__character_sheet__roster_entry__tenures__end_date__isnull=True,
            persona__character_sheet__roster_entry__tenures__player_data__account=request.user,
        ).exists()
