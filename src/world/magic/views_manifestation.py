"""The technique picker's read API (#4341).

``GET /api/magic/manifest-choices/?character_sheet=<id>`` lists what each manifesting
technique the character knows can bring into a fight. The owner reads their own
characters', staff anyone's. The write is the ``manifest_set`` action, dispatched.
"""

from __future__ import annotations

from django_filters import rest_framework as filters
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from world.character_sheets.models import CharacterSheet
from world.magic.serializers_manifestation import ManifestChoiceSerializer
from world.magic.services.manifestation import manifest_choices_for
from world.roster.models import RosterEntry
from world.stories.pagination import StandardResultsSetPagination


class ManifestChoiceFilter(filters.FilterSet):
    """Pick the one character whose choices are listed (required)."""

    character_sheet = filters.NumberFilter(field_name="pk", required=True)

    class Meta:
        model = CharacterSheet
        fields = ["character_sheet"]


class ManifestChoiceViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Each manifesting technique a character knows, its options and the current pick."""

    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.DjangoFilterBackend]
    filterset_class = ManifestChoiceFilter
    serializer_class = ManifestChoiceSerializer

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
        choices = manifest_choices_for(sheet) if sheet is not None else []
        page = self.paginate_queryset(choices)
        if page is not None:
            return self.get_paginated_response(ManifestChoiceSerializer(page, many=True).data)
        return Response(ManifestChoiceSerializer(choices, many=True).data)
