"""
Views for the character sheets API.
"""

from django.db.models import QuerySet
from rest_framework.mixins import RetrieveModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet

from world.character_sheets.models import CharacterSheet
from world.character_sheets.serializers import (
    CharacterSheetSerializer,
    get_character_sheet_queryset,
)


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
