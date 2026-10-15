"""API views for the worship foundation (#2355)."""

from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from world.roster.models import RosterEntry
from world.stories.pagination import StandardResultsSetPagination
from world.worship.exceptions import VisionError
from world.worship.models import Miracle, Prayer, Vision, WorshippedBeing, WorshipRite
from world.worship.prayer_services import send_vision
from world.worship.serializers import (
    InvocationOptionsSerializer,
    MiracleSerializer,
    PrayerSerializer,
    VisionCreateSerializer,
    VisionSerializer,
    WorshippedBeingRefSerializer,
    WorshipRiteSerializer,
)


def _entry_id_param(request: Request) -> int | None:
    """The tab's ``entry_id`` query parameter (#3479), or None when absent.

    The same identity parameter the mission journal reads; not a filter, so it
    is read here rather than through a FilterSet.
    """
    raw = request.query_params.get("entry_id")
    if raw in (None, ""):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError({"entry_id": "A valid integer is required."}) from exc


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

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "entry_id",
                int,
                required=False,
                description="The roster entry this tab acts as (#3479).",
            )
        ],
        responses=InvocationOptionsSerializer,
    )
    @action(detail=False, methods=["get"], url_path="invocation-options")
    def invocation_options(self, request: Request) -> Response:
        """The Call on favor picker for the acting character (#4333).

        Every being the character holds a standing with: favor, whether it can
        be invoked now (and why not), uses left this week and how hard the
        invocation check is with each ease; plus the bonus each outcome gives.
        """
        from world.roster.services.selection import character_for_request  # noqa: PLC0415
        from world.worship.invocation_services import (  # noqa: PLC0415
            invocation_bonus_table,
            invocation_options,
        )
        from world.worship.types import InvocationPicker  # noqa: PLC0415

        character = character_for_request(request, entry_id=_entry_id_param(request))
        sheet = character.character_sheet if character is not None else None
        if sheet is None:
            raise ValidationError({"detail": "Select a character first."})
        picker = InvocationPicker(
            beings=invocation_options(sheet), bonuses=invocation_bonus_table()
        )
        return Response(InvocationOptionsSerializer(picker).data)


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
