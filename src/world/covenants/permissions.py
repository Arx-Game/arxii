"""Permission classes for the covenants app."""

from __future__ import annotations

from rest_framework import permissions
from rest_framework.request import Request

from world.covenants.models import CharacterCovenantRole


class IsOwnMembership(permissions.BasePermission):
    """Permits action on a CharacterCovenantRole only if the requesting user
    currently plays the membership's character_sheet (active RosterTenure).

    Mirrors the Slice A list-view scoping predicate exactly:
        character_sheet__roster_entry__tenures__end_date__isnull=True
        character_sheet__roster_entry__tenures__player_data__account=user
    """

    def has_object_permission(
        self,
        request: Request,
        view: object,
        obj: CharacterCovenantRole,
    ) -> bool:
        if request.user.is_staff:
            return True
        # Walk the same chain as CharacterCovenantRoleViewSet.get_queryset:
        #   CharacterSheet → RosterEntry → RosterTenure → PlayerData → Account
        return CharacterCovenantRole.objects.filter(
            pk=obj.pk,
            character_sheet__roster_entry__tenures__end_date__isnull=True,
            character_sheet__roster_entry__tenures__player_data__account=request.user,
        ).exists()
