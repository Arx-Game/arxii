"""OOC friends-list (#1727) + rivalry-declaration (#2170) API — the web face of
world.scenes.friend_services.

A player's friendships (those made by any of their characters): list, add (one character or all),
remove. Rivalries mirror the same shape: list, declare (double opt-in — mutual only once both
sides declare), withdraw. Tenure-scoped + alt-private, mirroring the Block/Mute control API.
"""

from __future__ import annotations

from django.db.models import Exists, OuterRef, QuerySet
from rest_framework import mixins, serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from evennia_extensions.models import PlayerData
from world.scenes.friend_serializers import (
    FriendshipCreateSerializer,
    FriendshipSerializer,
    RivalryCreateSerializer,
    RivalrySerializer,
)
from world.scenes.friend_services import add_friend, add_friend_all_characters, declare_rival
from world.scenes.models import Friendship, Rivalry

_NO_ACTIVE_TENURE = "That character has no active tenure to friend."
_NO_ACTIVE_TENURE_RIVAL = "That character has no active tenure to declare a rival."


class FriendsPagination(PageNumberPagination):
    page_size = 100


class FriendshipViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    GenericViewSet,
):
    """The requesting player's OOC friends: list, add (this character or all), remove."""

    permission_classes = [IsAuthenticated]
    pagination_class = FriendsPagination
    filter_backends: list = []

    def get_queryset(self) -> QuerySet[Friendship]:
        return Friendship.objects.filter(
            friender_tenure__player_data__account=self.request.user
        ).select_related("friend_tenure__roster_entry__character_sheet__character")

    def get_serializer_class(self) -> type[serializers.BaseSerializer]:
        return FriendshipCreateSerializer if self.action == "create" else FriendshipSerializer

    def create(self, request: Request, *args: object, **kwargs: object) -> Response:
        serializer = FriendshipCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        # Resolve each character (RosterEntry) to its current tenure — friendships are tenure-based.
        friend_tenure = data["friend"].current_tenure
        viewer_tenure = data["viewer"].current_tenure
        if friend_tenure is None or viewer_tenure is None:
            raise serializers.ValidationError(_NO_ACTIVE_TENURE)
        if data["all_characters"]:
            player_data, _ = PlayerData.objects.get_or_create(account=request.user)
            add_friend_all_characters(player_data=player_data, friend_tenure=friend_tenure)
            return Response(status=status.HTTP_201_CREATED)
        friendship = add_friend(friender_tenure=viewer_tenure, friend_tenure=friend_tenure)
        return Response(FriendshipSerializer(friendship).data, status=status.HTTP_201_CREATED)


class RivalryViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    GenericViewSet,
):
    """The requesting player's rival declarations: list, declare, withdraw (#2170).

    Double opt-in — a declaration here is one side's intent; ``is_mutual`` flips true (and the
    RIVALS consent gate opens) only once the other side declares back. Withdrawing (DELETE)
    removes only your own side.
    """

    permission_classes = [IsAuthenticated]
    pagination_class = FriendsPagination
    filter_backends: list = []

    def get_queryset(self) -> QuerySet[Rivalry]:
        reciprocal = Rivalry.objects.filter(
            rivaler_tenure=OuterRef("rival_tenure"), rival_tenure=OuterRef("rivaler_tenure")
        )
        return (
            Rivalry.objects.filter(rivaler_tenure__player_data__account=self.request.user)
            .select_related("rival_tenure__roster_entry__character_sheet__character")
            .annotate(is_mutual=Exists(reciprocal))
            .order_by("-created_at")
        )

    def get_serializer_class(self) -> type[serializers.BaseSerializer]:
        return RivalryCreateSerializer if self.action == "create" else RivalrySerializer

    def create(self, request: Request, *args: object, **kwargs: object) -> Response:
        serializer = RivalryCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        # Resolve each character (RosterEntry) to its current tenure — rivalries are tenure-based.
        viewer_tenure = data["viewer"].current_tenure
        rival_tenure = data["rival"].current_tenure
        if viewer_tenure is None or rival_tenure is None:
            raise serializers.ValidationError(_NO_ACTIVE_TENURE_RIVAL)
        rivalry = declare_rival(rivaler_tenure=viewer_tenure, rival_tenure=rival_tenure)
        # The annotated list queryset supplies is_mutual; stamp it explicitly on the create path.
        rivalry.is_mutual = Rivalry.objects.filter(
            rivaler_tenure=rival_tenure, rival_tenure=viewer_tenure
        ).exists()
        return Response(RivalrySerializer(rivalry).data, status=status.HTTP_201_CREATED)
