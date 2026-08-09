"""Views for invitation-gated account registration (#3054).

``AccountInviteViewSet`` follows the project's staff-permission convention —
``IsAuthenticated + IsAdminUser`` (DRF's built-in ``request.user.is_staff``
check), a real ``FilterSet``, and explicit ``.order_by(...)`` for stable
pagination (see ``world.missions.views`` module docstring for the same
convention spelled out).
"""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from world.registration import services
from world.registration.filters import AccountInviteFilter
from world.registration.models import AccountInvite, get_registration_config
from world.registration.serializers import AccountInviteSerializer, IssueInviteSerializer
from world.stories.pagination import StandardResultsSetPagination


class RegistrationStatusView(APIView):
    """Public GET — whether registration is currently open. No invite enumeration."""

    permission_classes = [permissions.AllowAny]

    def get(self, request: Request, *args, **kwargs) -> Response:
        return Response({"open": get_registration_config().registration_open})


class AccountInviteViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Staff-only issue / list / revoke of per-email account invites."""

    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = AccountInviteFilter

    def get_queryset(self):
        return AccountInvite.objects.select_related("invited_by", "redeemed_by").order_by(
            "-created_at"
        )

    def get_serializer_class(self):
        if self.action == "create":
            return IssueInviteSerializer
        return AccountInviteSerializer

    def create(self, request: Request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invite = services.issue_invite(
            email=serializer.validated_data["email"],
            invited_by=request.user,
            note=serializer.validated_data.get("note", ""),
        )
        return Response(
            AccountInviteSerializer(invite).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def revoke(self, request: Request, pk=None) -> Response:
        invite = self.get_object()
        services.revoke_invite(invite, by=request.user)
        return Response(AccountInviteSerializer(invite).data)
