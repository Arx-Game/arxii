"""OOC friends-list API (#1727) — the web face of world.scenes.friend_services.

A player's friendships (those made by any of their characters): list, add (one character or all),
remove. Tenure-scoped + alt-private, mirroring the Block/Mute control API.
"""

from __future__ import annotations

from django.db.models import QuerySet
from rest_framework import mixins, serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from evennia_extensions.models import PlayerData
from world.scenes.friend_serializers import FriendshipCreateSerializer, FriendshipSerializer
from world.scenes.friend_services import add_friend, add_friend_all_characters
from world.scenes.models import Friendship


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
        if data["all_characters"]:
            player_data, _ = PlayerData.objects.get_or_create(account=request.user)
            add_friend_all_characters(player_data=player_data, friend_tenure=data["friend_tenure"])
            return Response(status=status.HTTP_201_CREATED)
        friendship = add_friend(
            friender_tenure=data["friender_tenure"], friend_tenure=data["friend_tenure"]
        )
        return Response(FriendshipSerializer(friendship).data, status=status.HTTP_201_CREATED)
