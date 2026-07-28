"""Permission classes for the tasking board API."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rest_framework.permissions import SAFE_METHODS, BasePermission

if TYPE_CHECKING:
    from rest_framework.request import Request

    from world.scenes.models import Persona


def active_persona_for_request(request: Request) -> Persona | None:
    """Resolve the request user's ACTIVE persona, or None (IC reads scope to it)."""
    from world.roster.models import RosterEntry  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    if not request.user.is_authenticated:
        return None
    entry = RosterEntry.objects.for_account(request.user).first()
    if entry is None:
        return None
    return active_persona_for_sheet(entry.character_sheet)


_CREATE_ACTION = "create"


class IsOrgLeaderForCreate(BasePermission):
    """Reads pass (queryset scoping handles visibility); creating a task needs
    org leadership. The assign action gates separately (any active member)."""

    message = "Only the organization's leadership can issue tasks."

    def has_permission(self, request: Request, view) -> bool:
        if request.method in SAFE_METHODS or view.action != _CREATE_ACTION:
            return True
        from world.societies.houses.services import is_org_leader  # noqa: PLC0415
        from world.societies.models import Organization  # noqa: PLC0415

        persona = active_persona_for_request(request)
        if persona is None:
            return False
        org_id = request.data.get("org")
        org = Organization.objects.filter(pk=org_id).first() if org_id else None
        if org is None:
            return False
        return is_org_leader(persona, org)
