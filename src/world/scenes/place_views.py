"""ViewSets for place management."""

from __future__ import annotations

from http import HTTPMethod
from typing import Any

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
    viewer_is_present = serializers.SerializerMethodField()

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
            "viewer_is_present",
        ]
        read_only_fields = ["id", "created_at"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Memoized per serializer instance so a list page's N rows share one
        # owned-persona lookup instead of re-running it per row (#2156 review fold-in).
        self._owned_persona_ids_cache: set[int] | None = None

    def _owned_persona_ids(self) -> set[int]:
        """Return (and cache) the requesting account's owned persona ids."""
        if self._owned_persona_ids_cache is None:
            request = self.context.get("request")
            if not (request and request.user and request.user.is_authenticated):
                self._owned_persona_ids_cache = set()
            else:
                self._owned_persona_ids_cache = set(get_account_personas(request))
        return self._owned_persona_ids_cache

    def get_presence_count(self, obj: Place) -> int:
        return PlacePresence.objects.filter(place=obj).count()

    def get_viewer_is_present(self, obj: Place) -> bool:
        """Whether one of the requesting account's personas is present at this place (#2156)."""
        owned = self._owned_persona_ids()
        return (
            bool(owned) and PlacePresence.objects.filter(place=obj, persona_id__in=owned).exists()
        )


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
