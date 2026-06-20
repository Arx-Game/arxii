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
    plays an active character in the same covenant whose rank has can_kick=True.

    Tier precedence (equal/higher-rank target) is enforced by the service layer
    (kick_member raises CannotKickEqualOrHigherRankError → 400), not here.
    This permission answers only: "is this user a kicker at all?"
    """

    def has_object_permission(
        self,
        request: Request,
        view: object,
        obj: CharacterCovenantRole,
    ) -> bool:
        if request.user.is_staff:
            return True
        # The actor must be: active, in the same covenant, can_kick=True.
        # Exclude the target's own membership (can't kick yourself via this path).
        return (
            CharacterCovenantRole.objects.filter(
                covenant_id=obj.covenant_id,
                left_at__isnull=True,
                rank__can_kick=True,
                character_sheet__roster_entry__tenures__end_date__isnull=True,
                character_sheet__roster_entry__tenures__player_data__account=request.user,
            )
            .exclude(pk=obj.pk)
            .exists()
        )


class CanInviteToCovenant(permissions.BasePermission):
    """Permits inviting to ``obj`` (a Covenant) only if the requester plays an
    active member whose rank has can_invite=True.

    Object-level: ``obj`` is a Covenant instance; checks the requester's active
    membership in that covenant.
    """

    def has_object_permission(
        self,
        request: Request,
        view: object,
        obj: object,
    ) -> bool:
        if request.user.is_staff:
            return True
        return CharacterCovenantRole.objects.filter(
            covenant=obj,
            left_at__isnull=True,
            rank__can_invite=True,
            character_sheet__roster_entry__tenures__end_date__isnull=True,
            character_sheet__roster_entry__tenures__player_data__account=request.user,
        ).exists()


class CanManageCovenantRanks(permissions.BasePermission):
    """Permits rank-management actions only if the requester plays an active member
    in the relevant covenant whose rank has can_manage_ranks=True.

    When used on a CovenantRank detail action the covenant is obtained from
    ``obj.covenant``; when used on a Covenant action it is ``obj`` directly.
    """

    def has_permission(self, request: Request, view: object) -> bool:
        # List/create actions: require authentication; object-level enforces the rest.
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(
        self,
        request: Request,
        view: object,
        obj: object,
    ) -> bool:
        if request.user.is_staff:
            return True
        # Support both CovenantRank objects (obj.covenant) and Covenant objects (obj).
        from world.covenants.models import Covenant, CovenantRank  # noqa: PLC0415

        if isinstance(obj, CovenantRank):
            covenant = obj.covenant
        elif isinstance(obj, Covenant):
            covenant = obj
        else:
            return False
        return CharacterCovenantRole.objects.filter(
            covenant=covenant,
            left_at__isnull=True,
            rank__can_manage_ranks=True,
            character_sheet__roster_entry__tenures__end_date__isnull=True,
            character_sheet__roster_entry__tenures__player_data__account=request.user,
        ).exists()
