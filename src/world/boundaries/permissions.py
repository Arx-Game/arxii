"""Permission classes for the boundaries API (#1771 task 6)."""

from __future__ import annotations

from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView

from world.boundaries.models import PlayerBoundary, TreasuredSubject


def _owner_player_data_id(obj: object) -> int | None:
    """The owning ``PlayerData`` id for a boundaries model instance.

    ``PlayerBoundary.owner`` IS a ``PlayerData``; ``TreasuredSubject.owner``
    is a ``RosterTenure``, one hop from ``PlayerData`` via ``player_data_id``.
    """
    if isinstance(obj, PlayerBoundary):
        return obj.owner_id
    if isinstance(obj, TreasuredSubject):
        return obj.owner.player_data_id
    return None


class IsOwnPlayerData(permissions.BasePermission):
    """Object access only for the player who owns the boundaries row.

    Self-authoring only — there is no "staff may view" carve-out here, since
    a hard-line row's ``detail`` must never be exposed to anyone but its
    author, staff included (ADR-0033).
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request: Request, view: APIView, obj: object) -> bool:
        if not hasattr(request.user, "player_data"):
            return False
        owner_player_data_id = _owner_player_data_id(obj)
        if owner_player_data_id is None:
            return False
        return owner_player_data_id == request.user.player_data.pk
