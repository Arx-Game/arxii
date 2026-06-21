"""Block / Mute player-control endpoints (#1278).

The API the persona context menu, the account-menu lists, and the telnet commands all call. A
player manages their *own* blocks and mutes; staff have no special path here (blocks are reviewed
via the admin / the contact-flag surface).
"""

from __future__ import annotations

from http import HTTPMethod

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import QuerySet
from rest_framework import mixins, serializers, status
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from evennia_extensions.models import PlayerData
from world.scenes.block_services import (
    create_block,
    request_unblock,
    share_block_account_wide,
)
from world.scenes.models import Block, Mute
from world.scenes.mute_services import set_mute, unmute
from world.scenes.social_control_serializers import (
    BlockCreateSerializer,
    BlockSerializer,
    MuteCreateSerializer,
    MuteSerializer,
)


class SocialControlPagination(PageNumberPagination):
    """Block/Mute lists are small; a generous page keeps them single-page in practice."""

    page_size = 100


class BlockViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    GenericViewSet,
):
    """The requesting player's blocks: list, create (with reason), unblock, share account-wide."""

    permission_classes = [IsAuthenticated]
    pagination_class = SocialControlPagination
    filter_backends: list = []

    def get_queryset(self) -> QuerySet[Block]:
        return Block.objects.filter(owner__account=self.request.user).select_related(
            "blocked_persona", "blocker_persona"
        )

    def get_serializer_class(self) -> type[serializers.BaseSerializer]:
        return BlockCreateSerializer if self.action == "create" else BlockSerializer

    def create(self, request: Request, *args: object, **kwargs: object) -> Response:
        serializer = BlockCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        try:
            block = create_block(
                blocker_account=request.user,
                blocker_persona=serializer.validated_data["blocker_persona"],
                blocked_persona=serializer.validated_data["blocked_persona"],
                reason=serializer.validated_data["reason"],
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return Response(BlockSerializer(block).data, status=status.HTTP_201_CREATED)

    def destroy(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Unblock — cron-delayed (the block stays active until the next sweep), so don't delete."""
        block = self.get_object()
        request_unblock(block)
        return Response(BlockSerializer(block).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=[HTTPMethod.POST])
    def share(self, request: Request, pk: int | None = None) -> Response:
        """Escalate this block to all of the requesting player's characters (#1278)."""
        block = self.get_object()
        share_block_account_wide(block)
        return Response(BlockSerializer(block).data)


class MuteViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    GenericViewSet,
):
    """The requesting player's mutes: list, create/update (IC/OOC scope), and unmute."""

    permission_classes = [IsAuthenticated]
    pagination_class = SocialControlPagination
    filter_backends: list = []

    def get_queryset(self) -> QuerySet[Mute]:
        return Mute.objects.filter(owner__account=self.request.user).select_related("muted_persona")

    def get_serializer_class(self) -> type[serializers.BaseSerializer]:
        return MuteCreateSerializer if self.action == "create" else MuteSerializer

    def create(self, request: Request, *args: object, **kwargs: object) -> Response:
        serializer = MuteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        owner, _ = PlayerData.objects.get_or_create(account=request.user)
        mute = set_mute(
            owner=owner,
            muted_persona=serializer.validated_data["muted_persona"],
            ic=serializer.validated_data["mute_ic"],
            ooc=serializer.validated_data["mute_ooc"],
        )
        return Response(MuteSerializer(mute).data, status=status.HTTP_201_CREATED)

    def destroy(self, request: Request, *args: object, **kwargs: object) -> Response:
        mute = self.get_object()
        unmute(owner=mute.owner, muted_persona=mute.muted_persona)
        return Response(status=status.HTTP_204_NO_CONTENT)
