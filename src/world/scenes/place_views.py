"""ViewSets for place management."""

from __future__ import annotations

from http import HTTPMethod

from django.db.models import QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from world.scenes.interaction_permissions import get_account_personas
from world.scenes.models import Persona
from world.scenes.place_filters import PlaceFilter
from world.scenes.place_models import Place, PlacePresence


class PlaceSerializer(serializers.ModelSerializer):
    presence_count = serializers.SerializerMethodField()

    class Meta:
        model = Place
        fields = [
            "id",
            "name",
            "description",
            "room",
            "status",
            "created_at",
            "presence_count",
        ]
        read_only_fields = ["id", "created_at"]

    def get_presence_count(self, obj: Place) -> int:
        return PlacePresence.objects.filter(place=obj).count()


class PlacePresenceSerializer(serializers.ModelSerializer):
    persona_name = serializers.CharField(source="persona.name", read_only=True)

    class Meta:
        model = PlacePresence
        fields = ["id", "place", "persona", "persona_name", "arrived_at"]
        read_only_fields = ["id", "arrived_at"]


class PlacePagination(PageNumberPagination):
    page_size = 20


class PlaceViewSet(viewsets.ModelViewSet):
    """ViewSet for managing places within rooms."""

    serializer_class = PlaceSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = PlacePagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = PlaceFilter
    http_method_names = ["get", "post"]

    def get_queryset(self) -> QuerySet[Place]:
        return Place.objects.filter(status="active").order_by("name")

    @action(detail=True, methods=[HTTPMethod.POST], url_path="join")
    def join(self, request: Request, pk: int | None = None) -> Response:
        """Join a place, via JoinPlaceAction."""
        from actions.definitions.places import JoinPlaceAction  # noqa: PLC0415

        try:
            place = Place.objects.get(pk=pk, status="active")
        except Place.DoesNotExist:
            return Response({"detail": "Place not found."}, status=status.HTTP_404_NOT_FOUND)
        persona_ids = get_account_personas(request)
        persona = (
            Persona.objects.filter(pk__in=persona_ids).select_related("character_sheet").first()
        )
        if persona is None:
            return Response(
                {"detail": "No personas found for your account."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        action_result = JoinPlaceAction().run(actor=persona.character_sheet.character, place=place)
        if not action_result.success:
            return Response({"detail": action_result.message}, status=status.HTTP_400_BAD_REQUEST)
        presence = action_result.data["presence"]
        return Response(PlacePresenceSerializer(presence).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=[HTTPMethod.POST], url_path="leave")
    def leave(self, request: Request, pk: int | None = None) -> Response:
        """Leave a place, via LeavePlaceAction."""
        from actions.definitions.places import LeavePlaceAction  # noqa: PLC0415

        try:
            place = Place.objects.get(pk=pk, status="active")
        except Place.DoesNotExist:
            return Response({"detail": "Place not found."}, status=status.HTTP_404_NOT_FOUND)
        persona_ids = get_account_personas(request)
        persona = (
            Persona.objects.filter(pk__in=persona_ids).select_related("character_sheet").first()
        )
        if persona is None:
            return Response(
                {"detail": "No personas found for your account."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        action_result = LeavePlaceAction().run(actor=persona.character_sheet.character, place=place)
        if not action_result.success:
            return Response({"detail": action_result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)
