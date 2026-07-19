"""API views for ceremonies (#2289).

Read-only: ceremony verbs (open/offering/speech/finish/abandon) are REGISTRY
actions reached through the generic player-action dispatch seam, exactly like
telnet. This ViewSet feeds the room ceremony card.
"""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet, ReadOnlyModelViewSet

from world.ceremonies.models import Ceremony
from world.ceremonies.serializers import CeremonySerializer, SeanceManifestationOfferSerializer
from world.stories.pagination import StandardResultsSetPagination


class CeremonyViewSet(ReadOnlyModelViewSet):
    """List/detail ceremonies, filterable by location and status."""

    serializer_class = CeremonySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    # location__objectdb lets the game view filter by the room object id it holds.
    filterset_fields = ["location", "location__objectdb", "status", "ceremony_type__key"]
    queryset = (
        Ceremony.objects.select_related("ceremony_type", "officiant", "presented_being", "location")
        # Bare-string prefetch is deliberate: Prefetch(to_attr=...) onto
        # SharedMemoryModel parents leaks across requests (identity map).
        .prefetch_related("honorees__honoree_sheet", "speeches__speaker")  # noqa: PREFETCH_STRING
        .order_by("-opened_at")
    )


class SeanceOfferViewSet(mixins.ListModelMixin, GenericViewSet):
    """PENDING seance-offer inbox for the requesting account (#2393).

    GET  /api/ceremonies/seance-offers/ — the caller's own PENDING offers,
    across every character sheet they've ever held (live, dead, or retired).
    Deliberately no pagination — this list is always small (bounded by how
    many open Seance ceremonies currently name this account's characters).
    POST .../{id}/accept/ — accept (mints the location move + retired-puppet grant).
    POST .../{id}/decline/ — decline.
    """

    serializer_class = SeanceManifestationOfferSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        from world.ceremonies.services import pending_seance_offers_for_account  # noqa: PLC0415

        return pending_seance_offers_for_account(self.request.user)

    def _respond(self, request: Request, pk: str | None, *, accept: bool) -> Response:
        from actions.definitions.ceremonies import RespondSeanceOfferAction  # noqa: PLC0415

        result = RespondSeanceOfferAction().run(
            actor=None, account=request.user, offer_id=pk, accept=accept
        )
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": result.message, **(result.data or {})})

    @action(detail=True, methods=["post"])
    def accept(self, request: Request, pk: str | None = None) -> Response:
        return self._respond(request, pk, accept=True)

    @action(detail=True, methods=["post"])
    def decline(self, request: Request, pk: str | None = None) -> Response:
        return self._respond(request, pk, accept=False)
