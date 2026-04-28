from typing import TYPE_CHECKING, Any, cast

from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, status, viewsets
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from world.narrative.filters import GemitFilter, NarrativeMessageDeliveryFilter, UserStoryMuteFilter
from world.narrative.models import Gemit, NarrativeMessageDelivery, UserStoryMute
from world.narrative.permissions import (
    IsDeliveryRecipientOrStaff,
    IsOwnStoryMuteOrStaff,
)
from world.narrative.serializers import (
    GemitCreateSerializer,
    GemitSerializer,
    NarrativeMessageDeliverySerializer,
    UserStoryMuteCreateSerializer,
    UserStoryMuteSerializer,
)
from world.narrative.services import broadcast_gemit
from world.stories.pagination import StandardResultsSetPagination

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from evennia.accounts.models import AccountDB
    from rest_framework.request import Request
    from rest_framework.serializers import BaseSerializer


class MyNarrativeMessagesView(ListAPIView):
    """List narrative message deliveries for the requesting account's character(s)."""

    serializer_class = NarrativeMessageDeliverySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = NarrativeMessageDeliveryFilter

    def get_queryset(self) -> "QuerySet[NarrativeMessageDelivery]":
        user = self.request.user
        return (
            NarrativeMessageDelivery.objects.filter(
                recipient_character_sheet__character__db_account=user,
            )
            .select_related(
                "message",
                "message__related_story",
                "recipient_character_sheet__character",
            )
            .order_by("-message__sent_at")
        )


class MarkNarrativeMessageAcknowledgedView(APIView):
    """POST endpoint that marks a delivery acknowledged (idempotent)."""

    permission_classes = [IsAuthenticated, IsDeliveryRecipientOrStaff]

    def post(self, request: "Request", pk: int, *args: Any, **kwargs: Any) -> Response:
        delivery = get_object_or_404(NarrativeMessageDelivery, pk=pk)
        self.check_object_permissions(request, delivery)
        if delivery.acknowledged_at is None:
            delivery.acknowledged_at = timezone.now()
            delivery.save(update_fields=["acknowledged_at"])
        serializer = NarrativeMessageDeliverySerializer(delivery)
        return Response(serializer.data, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Task 7.2: Gemit ViewSet
# ---------------------------------------------------------------------------


class GemitViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """Read-only list + staff-only create for Gemit records.

    GET /api/narrative/gemits/ — paginated list, any authenticated user.
    POST /api/narrative/gemits/ — staff-only broadcast.
    """

    queryset = (
        Gemit.objects.all()
        .select_related("sender_account", "related_era", "related_story")
        .order_by("-sent_at")
    )
    filterset_class = GemitFilter
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]

    def get_serializer_class(self) -> "type[BaseSerializer]":
        if self.action == "create":
            return GemitCreateSerializer
        return GemitSerializer

    def get_permissions(self) -> list[Any]:
        if self.action == "create":
            return [IsAuthenticated(), IsAdminUser()]
        return [IsAuthenticated()]

    def create(self, request: "Request", *args: Any, **kwargs: Any) -> Response:
        """Validate input, broadcast, and return GemitSerializer response."""
        serializer = GemitCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        gemit = broadcast_gemit(
            body=serializer.validated_data["body"],
            sender_account=cast("AccountDB", request.user),
            related_era=serializer.validated_data.get("related_era"),
            related_story=serializer.validated_data.get("related_story"),
        )
        return Response(GemitSerializer(gemit).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Task 7.3: UserStoryMute ViewSet
# ---------------------------------------------------------------------------


class UserStoryMuteViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Manage the requesting user's UserStoryMutes.

    GET    /api/narrative/story-mutes/      — list my mutes
    POST   /api/narrative/story-mutes/      — mute a story
    DELETE /api/narrative/story-mutes/{id}/ — unmute
    """

    filterset_class = UserStoryMuteFilter
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    permission_classes = [IsAuthenticated, IsOwnStoryMuteOrStaff]

    def get_queryset(self) -> "QuerySet[UserStoryMute]":
        """Scope to the requesting user's mutes."""
        return (
            UserStoryMute.objects.filter(account=self.request.user)
            .select_related("story")
            .order_by("-muted_at")
        )

    def get_serializer_class(self) -> "type[BaseSerializer]":
        if self.action == "create":
            return UserStoryMuteCreateSerializer
        return UserStoryMuteSerializer

    def create(self, request: "Request", *args: Any, **kwargs: Any) -> Response:
        """Create the mute and return a UserStoryMuteSerializer response."""
        serializer = UserStoryMuteCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        mute = serializer.save(account=request.user)
        return Response(UserStoryMuteSerializer(mute).data, status=status.HTTP_201_CREATED)

    def destroy(self, request: "Request", *args: Any, **kwargs: Any) -> Response:
        """Delete the mute. IsOwnStoryMuteOrStaff enforces ownership via get_object()."""
        mute = self.get_object()
        mute.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
