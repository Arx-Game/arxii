"""API views for estates (#1985).

Will authoring is web-first CRUD scoped to the account's own played
characters (404-not-filtered, mirroring the boundaries/custody privacy
posture). Settlements are visible to the will's executors (and staff);
claims to the claimant personas' players (and staff). The will-reading
itself is a REGISTRY action dispatched through ``action.run()``, not a
viewset verb.
"""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from world.estates.models import Bequest, EstateClaim, EstateSettlement, Will, WillExecutor
from world.estates.serializers import (
    BequestSerializer,
    EstateClaimSerializer,
    EstateSettlementSerializer,
    WillExecutorSerializer,
    WillSerializer,
)
from world.roster.models import RosterEntry
from world.stories.pagination import StandardResultsSetPagination


def _my_sheet_ids(user):
    return RosterEntry.objects.for_account(user).values("character_sheet_id")


class WillViewSet(ModelViewSet):
    """CRUD on my own characters' wills; frozen once a settlement opens."""

    queryset = Will.objects.all()
    serializer_class = WillSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["character_sheet"]

    def get_queryset(self):
        queryset = Will.objects.select_related("character_sheet").prefetch_related(
            "bequests",  # noqa: PREFETCH_STRING — no to_attr on SharedMemoryModel (leak)
            "executors__persona",  # noqa: PREFETCH_STRING
        )
        if self.request.user.is_staff:
            return queryset
        return queryset.filter(character_sheet_id__in=_my_sheet_ids(self.request.user))


class BequestViewSet(ModelViewSet):
    """CRUD on bequest lines of my own wills."""

    queryset = Bequest.objects.all()
    serializer_class = BequestSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["will", "kind"]

    def get_queryset(self):
        queryset = Bequest.objects.select_related("will__character_sheet")
        if self.request.user.is_staff:
            return queryset
        return queryset.filter(will__character_sheet_id__in=_my_sheet_ids(self.request.user))


class WillExecutorViewSet(ModelViewSet):
    """Tag/untag executors on my own wills."""

    queryset = WillExecutor.objects.all()
    serializer_class = WillExecutorSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["will"]

    def get_queryset(self):
        queryset = WillExecutor.objects.select_related("will__character_sheet", "persona")
        if self.request.user.is_staff:
            return queryset
        return queryset.filter(will__character_sheet_id__in=_my_sheet_ids(self.request.user))


class EstateSettlementViewSet(ReadOnlyModelViewSet):
    """Settlement status for executors (and staff) — feeds the settlement card."""

    queryset = EstateSettlement.objects.all()
    serializer_class = EstateSettlementSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["status", "character_sheet"]

    def get_queryset(self):
        queryset = EstateSettlement.objects.select_related("character_sheet")
        if self.request.user.is_staff:
            return queryset
        return queryset.filter(
            character_sheet__will__executors__persona__character_sheet_id__in=(
                _my_sheet_ids(self.request.user)
            )
        ).distinct()


class EstateClaimViewSet(ReadOnlyModelViewSet):
    """Inherited grievances, claimant-only (the holder is never notified)."""

    queryset = EstateClaim.objects.all()
    serializer_class = EstateClaimSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["settlement"]

    def get_queryset(self):
        queryset = EstateClaim.objects.select_related("item", "settlement")
        if self.request.user.is_staff:
            return queryset
        return queryset.filter(
            claimant_persona__character_sheet_id__in=_my_sheet_ids(self.request.user)
        )
