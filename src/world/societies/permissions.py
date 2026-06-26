"""DRF permissions for the societies membership API (#1511)."""

from __future__ import annotations

from django.db.models import Q
from rest_framework import permissions
from rest_framework.request import Request

from world.societies.models import OrganizationMembership


def active_persona_q(user, path: str = "persona") -> Q:
    """Return a Q object matching personas whose active tenure belongs to ``user``."""
    return Q(
        **{
            f"{path}__character_sheet__roster_entry__tenures__end_date__isnull": True,
            f"{path}__character_sheet__roster_entry__tenures__player_data__account": user,
        }
    )


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
        return (
            OrganizationMembership.objects.filter(
                pk=obj.pk,
            )
            .filter(
                active_persona_q(request.user, path="persona"),
            )
            .exists()
        )
