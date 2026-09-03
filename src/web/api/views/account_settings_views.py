"""Account-level security settings (#3591, ADR-0266).

The single web-writable switch on ``PlayerData`` today: the opt-in telnet
block that rides on opt-in 2FA. Modelled on ``VisibilitySettingsView``
(``world/roster/views/settings_views.py``) but scoped to the account, not a
character, so it reads ``request.user.player_data`` directly - the ``Account``
typeclass property (``src/typeclasses/accounts.py``) gets or creates the
``PlayerData`` row itself, so no fallback branch is needed here (ADR-0260).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from web.api.serializers import AccountSecuritySettingsSerializer

if TYPE_CHECKING:
    from rest_framework.request import Request


class AccountSecuritySettingsView(APIView):
    """``GET`` / ``PATCH`` ``/api/account/security-settings/`` for the signed-in account."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=AccountSecuritySettingsSerializer, tags=["account"])
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        player_data = request.user.player_data
        return Response(AccountSecuritySettingsSerializer(player_data).data)

    @extend_schema(
        request=AccountSecuritySettingsSerializer,
        responses=AccountSecuritySettingsSerializer,
        tags=["account"],
    )
    def patch(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        body = AccountSecuritySettingsSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        player_data = request.user.player_data
        player_data.block_telnet_login_with_2fa = body.validated_data["block_telnet_login_with_2fa"]
        player_data.save(update_fields=["block_telnet_login_with_2fa"])
        return Response(AccountSecuritySettingsSerializer(player_data).data)
