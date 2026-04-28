from typing import TYPE_CHECKING

from rest_framework.permissions import BasePermission

if TYPE_CHECKING:
    from django.db.models import Model
    from rest_framework.request import Request
    from rest_framework.views import APIView

    from world.narrative.models import NarrativeMessageDelivery
    from world.stories.models import Story


class IsDeliveryRecipientOrStaff(BasePermission):
    """Recipients can read/acknowledge their own deliveries; staff reads any."""

    def has_object_permission(
        self,
        request: "Request",
        view: "APIView",
        obj: "NarrativeMessageDelivery",
    ) -> bool:
        if request.user.is_staff:
            return True
        return obj.recipient_character_sheet.character.db_account == request.user


class IsStoryLeadGMOrStaff(BasePermission):
    """Lead GM of story.primary_table or staff may send OOC notices.

    View-level: requires authentication and either staff status or an
    existing GMProfile. Object-level: confirms the user is Lead GM of
    the story's primary_table (primary_table.gm == user.gm_profile) or staff.
    """

    message = "Only the Lead GM of this story or staff may send OOC notices."

    def has_permission(self, request: "Request", view: "APIView") -> bool:
        """Authenticated users only; object-level enforces Lead GM."""
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(
        self,
        request: "Request",
        view: "APIView",
        obj: "Story",
    ) -> bool:
        """Check Lead GM (primary_table.gm) or staff."""
        if not request.user.is_authenticated:
            return False
        if request.user.is_staff:
            return True

        from world.gm.models import GMProfile  # noqa: PLC0415

        try:
            gm_profile = request.user.gm_profile
        except GMProfile.DoesNotExist:
            return False

        if not obj.primary_table_id:
            return False
        return obj.primary_table.gm_id == gm_profile.pk


class IsOwnStoryMuteOrStaff(BasePermission):
    """Owners of a UserStoryMute (account == request.user) or staff may delete it."""

    message = "You may only manage your own story mutes."

    def has_permission(self, request: "Request", view: "APIView") -> bool:
        """Authenticated users only."""
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(
        self,
        request: "Request",
        view: "APIView",
        obj: "Model",
    ) -> bool:
        """Only the owning account or staff may delete the mute."""
        if request.user.is_staff:
            return True
        return obj.account_id == request.user.pk
