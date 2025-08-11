from rest_framework import permissions

from world.roster.models import RosterTenure


class IsOwnerOrStaff(permissions.BasePermission):
    """
    Permission to check if user owns the object or is staff.
    Used for PlayerMedia and other user-owned resources.
    """

    def has_object_permission(self, request, view, obj):
        # Staff can always modify anything
        if request.user.is_staff:
            return True

        # Check if user owns this object through player_data relationship
        return obj.player_data.account == request.user


class IsPlayerOrStaff(permissions.BasePermission):
    """
    Permission to check if user is the current player of a character or staff.
    Used for roster entry modifications that require character tenure.
    """

    def has_object_permission(self, request, view, obj):
        # Staff can always modify roster entries
        if request.user.is_staff:
            return True

        # Check if user has an active tenure for this roster entry's character
        try:
            player_data = request.user.player_data
            return RosterTenure.objects.filter(
                roster_entry=obj,
                player_data=player_data,
                start_date__isnull=False,
                end_date__isnull=True,
            ).exists()
        except AttributeError:
            # No player_data
            return False


class ReadOnlyOrOwner(permissions.BasePermission):
    """
    Permission for read-only access to everyone, but write access only to owners.
    Used for PlayerMedia viewsets where anyone can view but only owners can modify.
    """

    def has_permission(self, request, view):
        # Read permissions for any request
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions require authentication
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # Read permissions for safe methods
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions require ownership or staff
        return request.user.is_staff or obj.player_data.account == request.user


class StaffOnlyWrite(permissions.BasePermission):
    """
    Permission for read-only access to everyone, but write access only to staff.
    Used for roster entries and other administrative resources.
    """

    def has_permission(self, request, view):
        # Read permissions for any request
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions require staff
        return request.user and request.user.is_staff

    def has_object_permission(self, request, view, obj):
        # Read permissions for safe methods
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions require staff
        return request.user.is_staff
