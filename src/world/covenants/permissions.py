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


class CanKickFromCovenant(permissions.BasePermission):
    """Permits kicking ``obj`` (a target CharacterCovenantRole) only if the requester
    plays an active character holding an active leadership role in the same covenant,
    and ``obj`` is not their own membership. The 'cannot kick a leader' rule is enforced
    in the service layer (→ 400) for a specific message."""

    def has_object_permission(
        self,
        request: Request,
        view: object,
        obj: CharacterCovenantRole,
    ) -> bool:
        if request.user.is_staff:
            return True
        return (
            CharacterCovenantRole.objects.filter(
                covenant_id=obj.covenant_id,
                left_at__isnull=True,
                covenant_role__is_leadership=True,
                character_sheet__roster_entry__tenures__end_date__isnull=True,
                character_sheet__roster_entry__tenures__player_data__account=request.user,
            )
            .exclude(pk=obj.pk)
            .exists()
        )
