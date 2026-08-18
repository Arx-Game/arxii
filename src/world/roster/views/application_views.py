"""Staff review endpoints for roster-character applications (#3265)."""

from http import HTTPMethod

from django.db.models import QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from world.roster.filters import RosterApplicationFilterSet
from world.roster.models import RosterApplication
from world.roster.permissions import CanApproveApplications
from world.roster.serializers import (
    RosterApplicationApprovalSerializer,
    RosterApplicationDetailSerializer,
    RosterApplicationListSerializer,
)


class RosterApplicationPagination(PageNumberPagination):
    """Default pagination for the staff review queue."""

    page_size = 20


class RosterApplicationViewSet(viewsets.ReadOnlyModelViewSet):
    """Staff-only review queue for applications to existing roster characters.

    Distinct from character_creation's DraftApplication review (new player-made
    characters): this queue is players applying for staff-authored characters
    on the Available shelf.
    """

    serializer_class = RosterApplicationListSerializer
    permission_classes = [CanApproveApplications]
    filter_backends = [DjangoFilterBackend]
    filterset_class = RosterApplicationFilterSet
    pagination_class = RosterApplicationPagination

    def get_queryset(self) -> QuerySet[RosterApplication]:
        return RosterApplication.objects.select_related(
            "character__character",
            "player_data__account",
            "reviewed_by",
        ).order_by("applied_date")

    def filter_queryset(self, queryset: QuerySet[RosterApplication]) -> QuerySet[RosterApplication]:
        # The pending-only default (applied by RosterApplicationFilterSet.qs) is
        # a *list*-view convenience: the staff queue opens on what needs action.
        # Detail/review lookups go through get_object(), which also routes
        # through filter_queryset(); skipping the filterset there lets `review`
        # resolve an already-decided application and 400 instead of 404ing
        # before it gets the chance.
        if self.action != "list":
            return queryset
        return super().filter_queryset(queryset)

    def get_serializer_class(self) -> type[BaseSerializer]:
        if self.action == "retrieve":
            return RosterApplicationDetailSerializer
        return super().get_serializer_class()

    @action(detail=True, methods=[HTTPMethod.POST])
    def review(self, request: Request, pk: str | None = None) -> Response:
        """Approve or deny one pending application."""
        application = self.get_object()
        serializer = RosterApplicationApprovalSerializer(
            data=request.data,
            context={"request": request, "application": application},
        )
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        return Response(result)

    @action(detail=False, methods=[HTTPMethod.GET], url_path="pending-count")
    def pending_count(self, request: Request) -> Response:
        """Count of applications awaiting review, for the staff hub badge."""
        return Response({"count": RosterApplication.objects.pending().count()})
