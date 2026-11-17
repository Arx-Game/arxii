"""The Sineating row's read API (#5177).

``GET /api/magic/sineating-options/?character_sheet=<id>`` lists what the character can attach
to a pose now: a plea to make to each Sineater bonded to them who is here, and a plea to answer
for each one waiting for them. Only a character the requester plays reads it, an NPC a GM runs
included. ``POST /api/magic/soul-tether/sineating/decline/`` turns a waiting plea down.
"""

from __future__ import annotations

from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import mixins, serializers, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from world.character_sheets.models import CharacterSheet
from world.magic.serializers_sineating import (
    SineatingDeclineSerializer,
    SineatingOptionSerializer,
)
from world.magic.services.sineating import sineating_options_for
from world.scenes.models import Persona
from world.stories.pagination import StandardResultsSetPagination


class SineatingOptionPagination(StandardResultsSetPagination):
    """A character has a handful of Sineaters; the composer reads page one."""

    page_size = 50


class SineatingOptionFilter(filters.FilterSet):
    """Pick the one character whose options are listed (required)."""

    character_sheet = filters.NumberFilter(field_name="pk", required=True)

    class Meta:
        model = CharacterSheet
        fields = ["character_sheet"]


class SineatingOptionViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """What the requester's character can attach to a pose as a Sineating."""

    permission_classes = [IsAuthenticated]
    pagination_class = SineatingOptionPagination
    filter_backends = [filters.DjangoFilterBackend]
    filterset_class = SineatingOptionFilter
    serializer_class = SineatingOptionSerializer

    def get_queryset(self):
        played = Persona.objects.filter(pk__in=self.request.user.cached_persona_ids).values_list(
            "character_sheet_id", flat=True
        )
        return CharacterSheet.objects.filter(pk__in=list(played))

    def list(self, request, *args, **kwargs):
        sheet = self.filter_queryset(self.get_queryset()).first()
        rows = sineating_options_for(sheet) if sheet is not None else []
        page = self.paginate_queryset(rows)
        if page is not None:
            return self.get_paginated_response(SineatingOptionSerializer(page, many=True).data)
        return Response(SineatingOptionSerializer(rows, many=True).data)


class SineatingDeclineView(APIView):
    """POST /api/magic/soul-tether/sineating/decline/ turns a waiting plea down.

    Accepts ``{actor_sheet_id, sinner_sheet_id}``; answers ``{"detail": <what the Sinner is
    told the Sineater did>}``.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=SineatingDeclineSerializer,
        responses={
            200: inline_serializer(
                name="SineatingDeclineResult", fields={"detail": serializers.CharField()}
            )
        },
    )
    def post(self, request: Request) -> Response:
        serializer = SineatingDeclineSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        return Response({"detail": serializer.decline()})
