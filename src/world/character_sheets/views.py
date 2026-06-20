"""
Views for the character sheets API.
"""

from django.db.models import QuerySet
from django.http import Http404
from rest_framework.mixins import RetrieveModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet

from world.character_sheets.models import CharacterSheet
from world.character_sheets.serializers import (
    CharacterSheetSerializer,
    get_character_sheet_queryset,
)
from world.scenes.block_services import sheet_blocked_for_viewer


class CharacterSheetViewSet(RetrieveModelMixin, GenericViewSet):
    """Read-only detail endpoint for character sheets, keyed by character pk.

    Returns character sheet data for a single character. The response
    includes a `can_edit` flag based on whether the requesting user is
    the original creator or staff.
    """

    serializer_class = CharacterSheetSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = []

    def get_queryset(self) -> QuerySet[CharacterSheet]:
        """Return character sheets with related data."""
        return get_character_sheet_queryset()

    def get_object(self) -> CharacterSheet:
        """Resolve the sheet, but 404 if a block hides it from the viewer (#1278).

        A blocked viewer should find the character "might as well not exist" — a 404, not a
        "you're blocked" banner. Staff bypass blocks.
        """
        sheet = super().get_object()
        user = self.request.user
        if not user.is_staff and sheet_blocked_for_viewer(viewer_account=user, sheet=sheet):
            raise Http404
        return sheet
