from __future__ import annotations

from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView

from world.roster.models import RosterEntry
from world.scenes.models import Interaction


def get_account_roster_entries(request: Request) -> list[RosterEntry]:
    """Roster entries the authenticated account holds a current tenure on.

    A stateless read of ``Account.cached_roster_entries`` (ADR-0260, #3597); the
    only work here is the anonymous guard. Nothing is stored on the request.
    """
    user = request.user
    if not user.is_authenticated:
        return []
    return user.cached_roster_entries


def get_account_personas(request: Request) -> list[int]:
    """Every persona id (any type) on a sheet the authenticated account plays."""
    user = request.user
    if not user.is_authenticated:
        return []
    return user.cached_persona_ids


class IsInteractionWriter(permissions.BasePermission):
    """Only the writer can modify/delete their interaction."""

    def has_object_permission(self, request: Request, view: APIView, obj: Interaction) -> bool:
        persona_ids = get_account_personas(request)
        return obj.persona_id in persona_ids
