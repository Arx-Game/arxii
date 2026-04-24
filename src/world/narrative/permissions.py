from typing import TYPE_CHECKING

from rest_framework.permissions import BasePermission

if TYPE_CHECKING:
    from rest_framework.request import Request
    from rest_framework.views import APIView

    from world.narrative.models import NarrativeMessageDelivery


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
