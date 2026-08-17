"""Views for invitation-gated account registration (#3054).

``AccountInviteViewSet`` follows the project's staff-permission convention —
``IsAuthenticated + IsAdminUser`` (DRF's built-in ``request.user.is_staff``
check), a real ``FilterSet``, and explicit ``.order_by(...)`` for stable
pagination (see ``world.missions.views`` module docstring for the same
convention spelled out).
"""

import logging

from allauth.account.models import EmailAddress
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from world.registration import services
from world.registration.filters import AccountInviteFilter
from world.registration.models import AccountInvite, get_registration_config
from world.registration.serializers import (
    AccountInviteSerializer,
    IssueInviteSerializer,
    VerificationLinkRequestSerializer,
)
from world.stories.pagination import StandardResultsSetPagination

logger = logging.getLogger(__name__)


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

    @action(detail=True, methods=["post"])
    def resend(self, request: Request, pk=None) -> Response:
        """Mail the redemption link again, for an invitee who lost the first one.

        Refuses anything not currently redeemable: a redeemed, revoked or
        expired invite has no working link to send, so mailing one would only
        hand the recipient a dead end.
        """
        invite = self.get_object()
        if not invite.is_redeemable:
            return Response(
                {"detail": "Only a pending invite can be resent.", "status": invite.status},
                status=status.HTTP_400_BAD_REQUEST,
            )
        sent = services.send_invite_email(invite)
        if not sent:
            return Response(
                {"detail": "The invite could not be emailed. Use Copy Link instead."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(AccountInviteSerializer(invite).data)


class VerificationLinkView(APIView):
    """Staff POST — produce the email-verification link for an account (#3193).

    Email must not be the only route to a verified account: when the mail
    provider is down, staff copy this link and hand it over directly, the same
    trust model as the invite link staff already paste by hand. Staff-only, so
    the existence responses (404 unknown / 400 verified) are not an
    enumeration oracle. Link generation is logged for audit.
    """

    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def post(self, request: Request, *args, **kwargs) -> Response:
        serializer = VerificationLinkRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        try:
            link = services.build_verification_link(email)
        except EmailAddress.DoesNotExist:
            return Response(
                {"detail": "No account has that email address."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except services.AlreadyVerifiedError:
            return Response(
                {"detail": "That address is already verified."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        logger.info(
            "Staff %s generated a verification link for %s",
            request.user.username,
            email,
        )
        return Response({"email": email, "link": link})
