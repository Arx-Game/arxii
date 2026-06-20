"""Permission classes for the consent API."""

from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView

from world.consent.models import (
    SocialConsentCategoryRule,
    SocialConsentPreference,
    SocialConsentWhitelist,
)
from world.roster.models import RosterTenure


def _tenure_from_obj(obj: object) -> RosterTenure | None:
    """Extract the owning RosterTenure from a consent model instance.

    Handles SocialConsentPreference (.tenure), SocialConsentWhitelist
    (.owner_tenure), and SocialConsentCategoryRule (.preference.tenure).
    """
    if isinstance(obj, SocialConsentPreference):
        return obj.tenure
    if isinstance(obj, SocialConsentWhitelist):
        return obj.owner_tenure
    if isinstance(obj, SocialConsentCategoryRule):
        return obj.preference.tenure
    return None


class IsTenureOwner(permissions.BasePermission):
    """Object access only for the player who owns the related tenure."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request: Request, view: APIView, obj: object) -> bool:
        tenure = _tenure_from_obj(obj)
        if tenure is None:
            return False
        if not hasattr(request.user, "player_data"):
            return False
        player_data = request.user.player_data
        return tenure.player_data_id == player_data.pk
