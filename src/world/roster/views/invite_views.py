"""API views for game invites (#2483)."""

from __future__ import annotations

from http import HTTPMethod

from django.db.models import QuerySet
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from world.roster.models import GameInvite
from world.roster.serializers.invites import (
    GameInviteCreateSerializer,
    GameInviteResolveSerializer,
    GameInviteSerializer,
)
from world.roster.services.invite_services import (
    claim_game_invite,
    create_game_invite,
    resolve_invite,
    revoke_game_invite,
)


class GameInviteViewSet(viewsets.ModelViewSet):
    """Viewset for game invites.

    - Create: auth + trust-gated (service validates trust)
    - List: auth, returns only the inviter's own invites
    - Resolve: AllowAny, returns display-safe context for registration page
    - Claim: auth, links invite to the authenticated account
    - Revoke: auth, inviter or staff only
    """

    serializer_class = GameInviteSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]  # no delete/update via REST

    def get_queryset(self) -> QuerySet[GameInvite]:
        """Return only the requesting user's own sent invites."""
        try:
            player_data = self.request.user.player_data
        except AttributeError:
            return GameInvite.objects.none()
        return GameInvite.objects.filter(inviter=player_data).order_by("-created_at")

    def create(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Create a new game invite."""
        serializer = GameInviteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            player_data = request.user.player_data
        except AttributeError:
            return Response(
                {"detail": "Player data not found."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            invite = create_game_invite(
                inviter=player_data,
                message=serializer.validated_data["message"],
            )
        except PermissionError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response(
            GameInviteSerializer(invite).data,
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        permission_classes=[IsAuthenticated],
    )
    def revoke(self, request: Request, pk: int | None = None) -> Response:
        """Revoke an invite (inviter or staff only)."""
        invite = self.get_object()
        # Only the inviter or staff can revoke
        try:
            player_data = request.user.player_data
        except AttributeError:
            player_data = None
        if not request.user.is_staff and invite.inviter != player_data:
            return Response(
                {"detail": "You can only revoke your own invites."},
                status=status.HTTP_403_FORBIDDEN,
            )
        revoke_game_invite(invite, revoked_by=request.user)  # type: ignore[arg-type]
        return Response({"detail": "Invite revoked."}, status=status.HTTP_200_OK)

    @action(
        detail=False,
        methods=[HTTPMethod.POST],
        permission_classes=[IsAuthenticated],
    )
    def claim(self, request: Request) -> Response:
        """Claim an invite token (first-login flow)."""
        token = request.data.get("token")
        if not token:
            return Response(
                {"detail": "token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            invite = claim_game_invite(token=token, account=request.user)  # type: ignore[arg-type]
        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            GameInviteSerializer(invite).data,
            status=status.HTTP_200_OK,
        )

    @action(
        detail=False,
        methods=[HTTPMethod.GET],
        permission_classes=[AllowAny],
    )
    def resolve(self, request: Request) -> Response:
        """Resolve a token to display-safe invite context (for registration page).

        AllowAny — this is called before the user has an account. Returns only
        the inviter's display name and message, never account info.
        """
        token = request.query_params.get("token")  # noqa: USE_FILTERSET
        if token is None:
            return Response(
                {"detail": "token parameter is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        invite = resolve_invite(token)
        if invite is None:
            return Response(
                {"detail": "Invite not found or no longer available."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            GameInviteResolveSerializer(invite).data,
            status=status.HTTP_200_OK,
        )
