"""Per-character visibility-settings API (#1484, #1463 follow-up).

The web control for quiet/hidden mode (``appear_offline``). Telnet has ``hide``/``unhide``; this is
the web equivalent — the frontend is the primary interface, so a switch was missing. Scoped to the
requesting player's **active character**: reads/writes that character's own
``TenureDisplaySettings`` via the existing ``set_appear_offline`` write path (never duplicated).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from world.roster.selectors import puppeted_sheet_for
from world.roster.serializers.settings import VisibilitySettingsSerializer
from world.roster.services.display import set_appear_offline

if TYPE_CHECKING:
    from rest_framework.request import Request

    from world.roster.models import RosterTenure


class VisibilitySettingsView(APIView):
    """GET / PATCH the active character's own visibility prefs (#1484).

    ``GET  /api/roster/visibility-settings/``  → current ``appear_offline``.
    ``PATCH /api/roster/visibility-settings/`` → set it (reuses ``set_appear_offline``).

    Scoped to the requesting player's currently-played character (its current tenure); a request
    with no played character is rejected uniformly. A player can only ever read/write their own
    character's settings — there is no cross-character access.
    """

    permission_classes = [IsAuthenticated]

    def _current_tenure(self, request: Request) -> RosterTenure:
        """The played character's current tenure, or raise a uniform validation error."""
        sheet = puppeted_sheet_for(request.user)
        entry = sheet.roster_entry_or_none if sheet is not None else None
        tenure = entry.current_tenure if entry is not None else None
        if tenure is None:
            msg = "You must be playing a character to change its visibility."
            raise serializers.ValidationError(msg)
        return tenure

    @extend_schema(responses=VisibilitySettingsSerializer, tags=["roster"])
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Return the active character's current ``appear_offline`` value."""
        tenure = self._current_tenure(request)
        settings_obj = getattr(tenure, "display_settings", None)  # noqa: GETATTR_LITERAL
        appear_offline = bool(settings_obj.appear_offline) if settings_obj is not None else False
        return Response(VisibilitySettingsSerializer({"appear_offline": appear_offline}).data)

    @extend_schema(
        request=VisibilitySettingsSerializer,
        responses=VisibilitySettingsSerializer,
        tags=["roster"],
    )
    def patch(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Set the active character's ``appear_offline`` (quiet/hidden mode)."""
        body = VisibilitySettingsSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        tenure = self._current_tenure(request)
        value = set_appear_offline(tenure=tenure, value=body.validated_data["appear_offline"])
        return Response(
            VisibilitySettingsSerializer({"appear_offline": value}).data,
            status=status.HTTP_200_OK,
        )
