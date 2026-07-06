"""Companion API views (#672).

Read surface + write endpoints (bind/release/fight/deploy) that converge on
``action.run()`` via ``PuppetActorMixin`` — the same pattern as
``SanctumViewSet`` (#1497).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from actions.definitions.companions import (
    BindCompanionAction,
    CompanionFightAction,
    DeployCompanionAction,
    OrderCompanionAction,
    ReleaseCompanionAction,
)
from world.companions.filters import CompanionFilterSet
from world.companions.models import Companion, CompanionArchetype
from world.companions.serializers import (
    BindActionSerializer,
    CompanionArchetypeSerializer,
    CompanionSerializer,
    OrderActionSerializer,
)
from world.magic.views_actor import PuppetActorMixin

if TYPE_CHECKING:
    from rest_framework.request import Request

    from world.scenes.models import Persona


class CompanionPagination(PageNumberPagination):
    page_size = 50


#: Error detail returned when the request has no active character to act as.
NO_ACTIVE_CHARACTER_DETAIL = "No active character."


def _active_persona_for_request(request: Request) -> Persona | None:
    """Resolve the request user's ACTIVE persona, or None if unresolvable.

    Mirrors world.ships.views._active_persona_for_request.
    """
    from world.roster.models import RosterEntry  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    if not request.user.is_authenticated:
        return None
    entry = RosterEntry.objects.for_account(request.user).first()
    if entry is None:
        return None
    return active_persona_for_sheet(entry.character_sheet)


class CompanionViewSet(PuppetActorMixin, viewsets.ReadOnlyModelViewSet):
    """Read + action endpoints for the player's companion surface.

    `list`/`retrieve` return the caller's own active companions (read-only).
    POST actions delegate to the four Actions in
    ``actions/definitions/companions.py``; ``ActionResult`` fields map 1:1 to
    the response bodies so the contract matches ``SanctumViewSet`` (#1918).
    """

    serializer_class = CompanionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CompanionPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = CompanionFilterSet

    def get_queryset(self):
        persona = _active_persona_for_request(self.request)
        if persona is None:
            return Companion.objects.none()
        return Companion.objects.filter(
            owner=persona.character_sheet, released_at__isnull=True
        ).select_related("archetype")

    # ------------------------------------------------------------------
    # Write endpoints — converge on action.run()
    # ------------------------------------------------------------------

    @action(detail=False, methods=["post"], url_path="bind")
    def bind(self, request):
        """Bind a new companion — ``POST /api/companions/companions/bind/``.

        Body: ``{archetype_id, gift_id, name}``.
        Wraps :class:`actions.definitions.companions.BindCompanionAction`.
        """
        serializer = BindActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = self._resolve_actor(request)
        if actor is None:
            return Response(
                {"detail": NO_ACTIVE_CHARACTER_DETAIL}, status=status.HTTP_400_BAD_REQUEST
            )
        result = BindCompanionAction().run(
            actor=actor,
            archetype_id=serializer.validated_data["archetype_id"],
            gift_id=serializer.validated_data["gift_id"],
            name=serializer.validated_data["name"],
        )
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="release")
    def release(self, request, pk=None):
        """Release a bonded companion — ``POST /api/companions/companions/{id}/release/``.

        Wraps :class:`actions.definitions.companions.ReleaseCompanionAction`.
        The companion id comes from the URL; ``get_queryset`` scopes it to the
        caller's active companions (foreign → 404). The Action re-validates
        ownership via ``_resolve_owned_companion`` (defense in depth).
        """
        companion = self.get_object()
        actor = self._resolve_actor(request)
        if actor is None:
            return Response(
                {"detail": NO_ACTIVE_CHARACTER_DETAIL}, status=status.HTTP_400_BAD_REQUEST
            )
        result = ReleaseCompanionAction().run(actor=actor, companion_id=companion.pk)
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result.data)

    @action(detail=True, methods=["post"], url_path="fight")
    def fight(self, request, pk=None):
        """Commit a companion into combat — ``POST /api/companions/companions/{id}/fight/``.

        Wraps :class:`actions.definitions.companions.CompanionFightAction`.
        """
        companion = self.get_object()
        actor = self._resolve_actor(request)
        if actor is None:
            return Response(
                {"detail": NO_ACTIVE_CHARACTER_DETAIL}, status=status.HTTP_400_BAD_REQUEST
            )
        result = CompanionFightAction().run(actor=actor, companion_id=companion.pk)
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result.data)

    @action(detail=True, methods=["post"], url_path="deploy")
    def deploy(self, request, pk=None):
        """Deploy a companion into a battle — ``POST /api/companions/companions/{id}/deploy/``.

        Wraps :class:`actions.definitions.companions.DeployCompanionAction`.
        """
        companion = self.get_object()
        actor = self._resolve_actor(request)
        if actor is None:
            return Response(
                {"detail": NO_ACTIVE_CHARACTER_DETAIL}, status=status.HTTP_400_BAD_REQUEST
            )
        result = DeployCompanionAction().run(actor=actor, companion_id=companion.pk)
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result.data)

    @action(detail=True, methods=["post"], url_path="order")
    def order(self, request, pk=None):
        """Order a deployed companion — ``POST /api/companions/companions/{id}/order/``.

        Wraps :class:`actions.definitions.companions.OrderCompanionAction` (#1921).
        """
        serializer = OrderActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        companion = self.get_object()
        actor = self._resolve_actor(request)
        if actor is None:
            return Response(
                {"detail": NO_ACTIVE_CHARACTER_DETAIL}, status=status.HTTP_400_BAD_REQUEST
            )
        result = OrderCompanionAction().run(
            actor=actor,
            companion_id=companion.pk,
            order_kind=serializer.validated_data["order_kind"],
            target_id=serializer.validated_data.get("target_id"),
            ability_id=serializer.validated_data.get("ability_id"),
            ally_id=serializer.validated_data.get("ally_id"),
        )
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result.data)


class CompanionArchetypeViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only catalog of authored CompanionArchetype rows."""

    queryset = CompanionArchetype.objects.all()
    serializer_class = CompanionArchetypeSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
