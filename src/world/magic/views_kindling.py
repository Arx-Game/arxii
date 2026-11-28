"""The "Your resonances" panel's read API (#5124).

``GET /api/magic/kindled-resonances/?character_sheet=<id>`` lists each resonance the
character holds with whether it is kindled, how strongly and why. The owner reads their own
characters', staff anyone's. The scene sidebar and the combat rail both read it, so the list
is computed once per request, never per row.
"""

from __future__ import annotations

from django_filters import rest_framework as filters
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from world.character_sheets.models import CharacterSheet
from world.magic.models import RecordedAct
from world.magic.serializers_kindling import (
    ImpulseSerializer,
    KindledResonanceSerializer,
    RecordedActSerializer,
)
from world.magic.services.gain import waiting_trickles
from world.magic.services.impulses import impulses_now, safe_refresh_impulses_for_character
from world.magic.services.kindling import kindled_resonances_now
from world.magic.services.marking import pointable_acts_queryset
from world.roster.models import RosterEntry
from world.stories.pagination import StandardResultsSetPagination


class KindledResonancePagination(StandardResultsSetPagination):
    """One page holds every resonance a character can hold; the panel reads only page one.

    The response carries an ``impulses`` list beside ``results`` (#5177)."""

    page_size = 100

    def get_paginated_response_schema(self, schema: dict) -> dict:
        """Document the ``impulses`` list the list view adds beside the page."""
        base = super().get_paginated_response_schema(schema)
        base["properties"]["impulses"] = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "resonance_id": {"type": "integer"},
                    "resonance_name": {"type": "string"},
                    "label": {"type": "string"},
                    "present": {"type": "boolean"},
                    "is_compulsion": {"type": "boolean"},
                    "text": {"type": "string"},
                    "reasons": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "resonance_id",
                    "resonance_name",
                    "label",
                    "present",
                    "is_compulsion",
                    "text",
                    "reasons",
                ],
            },
        }
        base["required"] = [*base.get("required", []), "impulses"]
        return base


class KindledResonanceFilter(filters.FilterSet):
    """Pick the one character whose resonances are listed (required)."""

    character_sheet = filters.NumberFilter(field_name="pk", required=True)

    class Meta:
        model = CharacterSheet
        fields = ["character_sheet"]


class KindledResonanceViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Each resonance a character holds, kindled or not, with the strength word and reasons."""

    permission_classes = [IsAuthenticated]
    pagination_class = KindledResonancePagination
    filter_backends = [filters.DjangoFilterBackend]
    filterset_class = KindledResonanceFilter
    serializer_class = KindledResonanceSerializer

    def get_queryset(self):
        qs = CharacterSheet.objects.all()
        if self.request.user.is_staff:
            return qs
        own = RosterEntry.objects.playable_by(self.request.user).values_list(
            "character_sheet_id", flat=True
        )
        return qs.filter(pk__in=list(own))

    def _impulses(self, sheet: CharacterSheet | None) -> list:
        """The character's impulses. Their own view applies what they call for (the
        Compulsion's condition, the once-per-scene words); staff reading another's sheet only
        reads."""
        if sheet is None:
            return []
        own = RosterEntry.objects.for_account(self.request.user).filter(character_sheet_id=sheet.pk)
        if own.exists():
            refreshed = safe_refresh_impulses_for_character(sheet.character)
            return list(refreshed.impulses) if refreshed is not None else []
        return impulses_now(sheet)

    def list(self, request, *args, **kwargs):
        sheet = self.filter_queryset(self.get_queryset()).first()
        rows = kindled_resonances_now(sheet) if sheet is not None else []
        impulses = ImpulseSerializer(self._impulses(sheet), many=True).data
        # What their days have piled up for the next anima ritual to harvest (#5308): read
        # once for the whole page.
        context = {"trickle": waiting_trickles(sheet) if sheet is not None else {}}
        page = self.paginate_queryset(rows)
        if page is not None:
            response = self.get_paginated_response(
                KindledResonanceSerializer(page, many=True, context=context).data
            )
        else:
            response = Response(
                {"results": KindledResonanceSerializer(rows, many=True, context=context).data}
            )
        response.data = {**dict(response.data), "impulses": impulses}
        return response


class RecordedActPagination(StandardResultsSetPagination):
    """Acts stay pointable for ``KindlingConfig.recorded_act_days``; the picker reads page one."""

    page_size = 50


class RecordedActFilter(filters.FilterSet):
    """Pick the one character whose acts are listed (required)."""

    character_sheet = filters.NumberFilter(field_name="character_sheet_id", required=True)

    class Meta:
        model = RecordedAct
        fields = ["character_sheet"]


class RecordedActViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """The acts a character can point a mark at (#5327), newest first.

    ``GET /api/magic/recorded-acts/?character_sheet=<id>`` lists only unmarked acts inside the
    pointable window (``KindlingConfig.recorded_act_days``), each with the resonances situations
    suggested for it, strongest first. A player reads the acts of the characters they play now
    (a borrower of a lent NPC, never the holder who lent it away), staff anyone's; another
    player's character is an empty page. Nothing here writes: an act is written by
    ``award_kindled_deeds`` and marked by a pose or journal entry.
    """

    permission_classes = [IsAuthenticated]
    pagination_class = RecordedActPagination
    filter_backends = [filters.DjangoFilterBackend]
    filterset_class = RecordedActFilter
    serializer_class = RecordedActSerializer

    def get_queryset(self):
        qs = pointable_acts_queryset()
        if not self.request.user.is_staff:
            own = RosterEntry.objects.playable_by(self.request.user).values_list(
                "character_sheet_id", flat=True
            )
            qs = qs.filter(character_sheet_id__in=list(own))
        return qs
