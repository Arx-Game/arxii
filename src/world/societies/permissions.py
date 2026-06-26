"""DRF permissions for the societies membership API (#1511)."""

from __future__ import annotations

from rest_framework import permissions
from rest_framework.request import Request

from world.societies.models import Organization, OrganizationMembership


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


class CanInviteToOrganization(permissions.BasePermission):
    """Permit inviting to an organization if the user plays an active inviter."""

    def has_object_permission(
        self,
        request: Request,
        view: object,
        obj: Organization,
    ) -> bool:
        if request.user.is_staff:
            return True
        return OrganizationMembership.objects.filter(
            organization=obj,
            left_at__isnull=True,
            exiled_at__isnull=True,
            rank__can_invite=True,
            persona__character_sheet__roster_entry__tenures__end_date__isnull=True,
            persona__character_sheet__roster_entry__tenures__player_data__account=request.user,
        ).exists()


class CanKickFromOrganization(permissions.BasePermission):
    """Permit kicking a target membership if the user plays an active kicker."""

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
                organization_id=obj.organization_id,
                left_at__isnull=True,
                exiled_at__isnull=True,
                rank__can_kick=True,
                persona__character_sheet__roster_entry__tenures__end_date__isnull=True,
                persona__character_sheet__roster_entry__tenures__player_data__account=request.user,
            )
            .exclude(pk=obj.pk)
            .exists()
        )


class CanManageOrganizationRanks(permissions.BasePermission):
    """Permit rank management if the user plays an active rank-manager."""

    def has_object_permission(
        self,
        request: Request,
        view: object,
        obj: Organization,
    ) -> bool:
        if request.user.is_staff:
            return True
        return OrganizationMembership.objects.filter(
            organization=obj,
            left_at__isnull=True,
            exiled_at__isnull=True,
            rank__can_manage_ranks=True,
            persona__character_sheet__roster_entry__tenures__end_date__isnull=True,
            persona__character_sheet__roster_entry__tenures__player_data__account=request.user,
        ).exists()
