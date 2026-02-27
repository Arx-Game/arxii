"""
Views for the character sheets API.
"""

from django.db.models import QuerySet
from django.db.models.query import Prefetch
from rest_framework.mixins import RetrieveModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet

from world.character_sheets.serializers import CharacterSheetSerializer
from world.forms.models import CharacterForm, CharacterFormValue, FormType
from world.progression.models import CharacterPathHistory
from world.roster.models import RosterEntry


class CharacterSheetViewSet(RetrieveModelMixin, GenericViewSet):
    """
    Read-only detail endpoint for character sheets, keyed by RosterEntry pk.

    Returns character sheet data for a single roster entry. The response
    includes a `can_edit` flag based on whether the requesting user is
    the original creator or staff.
    """

    serializer_class = CharacterSheetSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = []

    def get_queryset(self) -> QuerySet[RosterEntry]:
        """Return roster entries with related data for character sheets."""
        return RosterEntry.objects.select_related(
            "character",
            # CharacterSheet FK lookups
            "character__sheet_data__gender",
            "character__sheet_data__species",
            "character__sheet_data__heritage",
            "character__sheet_data__family",
            "character__sheet_data__tarot_card",
            "character__sheet_data__origin_realm",
            "character__sheet_data__build",
        ).prefetch_related(
            # can_edit check
            "tenures__player_data__account",
            # Path history (newest first for latest-path lookup)
            Prefetch(
                "character__path_history",
                queryset=(
                    CharacterPathHistory.objects.select_related("path").order_by("-selected_at")
                ),
            ),
            # TRUE forms with their trait values
            Prefetch(
                "character__forms",
                queryset=CharacterForm.objects.filter(form_type=FormType.TRUE),
            ),
            Prefetch(
                "character__forms__values",
                queryset=(CharacterFormValue.objects.select_related("trait", "option")),
            ),
        )
