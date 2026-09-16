"""API views for the worship foundation (#2355)."""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from world.roster.models import RosterEntry
from world.stories.pagination import StandardResultsSetPagination
from world.worship.exceptions import VisionError
from world.worship.models import Miracle, Prayer, Vision, WorshippedBeing, WorshipRite
from world.worship.prayer_services import send_vision
from world.worship.serializers import (
    MiracleSerializer,
    PrayerSerializer,
    VisionCreateSerializer,
    VisionSerializer,
    WorshippedBeingRefSerializer,
    WorshipRiteSerializer,
)


class WorshippedBeingViewSet(ReadOnlyModelViewSet):
    """Public catalog of active worshippable beings (the CG picker source).

    Exposes only the reference shape (id, name, tradition name) — pools,
    avatars, and worshipper lists never leave this endpoint.
    """

    serializer_class = WorshippedBeingRefSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["tradition"]
    search_fields = ["name"]
    queryset = WorshippedBeing.objects.filter(is_active=True).select_related("tradition")


class MiracleViewSet(ReadOnlyModelViewSet):
    """Staff-facing miracle catalog browser (#2360)."""

    serializer_class = MiracleSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    queryset = Miracle.objects.select_related("being")


class WorshipRiteViewSet(ReadOnlyModelViewSet):
    """The rites a being offers (#3777): what a worshipper can perform."""

    serializer_class = WorshipRiteSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["being", "kind__tier"]
    search_fields = ["name"]
    queryset = (
        WorshipRite.objects.filter(is_active=True, being__is_active=True)
        .select_related("being", "kind", "check_type", "resonance__resonance")
        .order_by("being__name", "kind__tier", "name")
    )


_STAFF_ONLY_VISIONS = "Only staff send visions."


def _own_sheet_ids(request) -> list[int]:
    """The sheets the requesting account holds a current tenure on (IC reads scope to
    the account's own characters). Queried, not read off the typeclass cache, so a
    bare ``AccountDB`` row (a test user, an API-only account) answers too."""
    return list(
        RosterEntry.objects.for_account(request.user).values_list("character_sheet_id", flat=True)
    )


class PrayerViewSet(ReadOnlyModelViewSet):
    """A character's prayers (#3779): the owner reads their own, staff read anyone's."""

    serializer_class = PrayerSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["character_sheet", "being"]

    def get_queryset(self):
        qs = Prayer.objects.select_related("being", "character_sheet")
        if self.request.user.is_staff:
            return qs
        return qs.filter(character_sheet_id__in=_own_sheet_ids(self.request))


class VisionViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """Visions (#3779): the recipient reads their own, staff read anyone's and send new ones."""

    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["recipient", "being"]

    def get_serializer_class(self):
        if self.action == "create":
            return VisionCreateSerializer
        return VisionSerializer

    def get_queryset(self):
        qs = Vision.objects.select_related("being", "recipient", "clue", "episode")
        if self.request.user.is_staff:
            return qs
        return qs.filter(recipient_id__in=_own_sheet_ids(self.request))

    def create(self, request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied(_STAFF_ONLY_VISIONS)
        serializer = VisionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            vision = send_vision(sent_by=request.user, **serializer.validated_data)
        except VisionError as exc:
            raise ValidationError({"detail": exc.user_message}) from exc
        out = VisionSerializer(vision, context=self.get_serializer_context())
        return Response(out.data, status=status.HTTP_201_CREATED)
