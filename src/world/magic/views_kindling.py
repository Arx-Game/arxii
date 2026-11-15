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
from world.magic.serializers_kindling import KindledResonanceSerializer
from world.magic.services.kindling import kindled_resonances_now
from world.roster.models import RosterEntry
from world.stories.pagination import StandardResultsSetPagination


class KindledResonancePagination(StandardResultsSetPagination):
    """One page holds every resonance a character can hold; the panel reads only page one."""

    page_size = 100


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
        own = RosterEntry.objects.for_account(self.request.user).values_list(
            "character_sheet_id", flat=True
        )
        return qs.filter(pk__in=list(own))

    def list(self, request, *args, **kwargs):
        sheet = self.filter_queryset(self.get_queryset()).first()
        rows = kindled_resonances_now(sheet) if sheet is not None else []
        page = self.paginate_queryset(rows)
        if page is not None:
            return self.get_paginated_response(KindledResonanceSerializer(page, many=True).data)
        return Response(KindledResonanceSerializer(rows, many=True).data)
