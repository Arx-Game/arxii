"""The "Reflecting on" row's read API (#5124).

``GET /api/magic/reflectables/?character_sheet=<id>`` lists what the character can reflect on
now: the resonance unsettling them (when they are unsettled), then each kindled deed they have
not reflected on. Only the owner reads it: a reflection is the writer's own business, so staff
get no wider view here.
"""

from __future__ import annotations

from django_filters import rest_framework as filters
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from world.character_sheets.models import CharacterSheet
from world.magic.serializers_reflection import ReflectionOptionSerializer
from world.magic.services.reflection import reflectable_for
from world.roster.models import RosterEntry
from world.stories.pagination import StandardResultsSetPagination


class ReflectablePagination(StandardResultsSetPagination):
    """The composer reads page one; a long run of deeds pages."""

    page_size = 50


class ReflectableFilter(filters.FilterSet):
    """Pick the one character whose choices are listed (required)."""

    character_sheet = filters.NumberFilter(field_name="pk", required=True)

    class Meta:
        model = CharacterSheet
        fields = ["character_sheet"]


class ReflectableViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """What the requester's character can reflect on, as the "Reflecting on" row's options."""

    permission_classes = [IsAuthenticated]
    pagination_class = ReflectablePagination
    filter_backends = [filters.DjangoFilterBackend]
    filterset_class = ReflectableFilter
    serializer_class = ReflectionOptionSerializer

    def get_queryset(self):
        own = RosterEntry.objects.for_account(self.request.user).values_list(
            "character_sheet_id", flat=True
        )
        return CharacterSheet.objects.filter(pk__in=list(own))

    def list(self, request, *args, **kwargs):
        sheet = self.filter_queryset(self.get_queryset()).first()
        rows = list(reflectable_for(sheet).options) if sheet is not None else []
        page = self.paginate_queryset(rows)
        if page is not None:
            return self.get_paginated_response(ReflectionOptionSerializer(page, many=True).data)
        return Response(ReflectionOptionSerializer(rows, many=True).data)
