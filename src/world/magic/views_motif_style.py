"""Motif style-binding API views (#2030).

Web DRF surface over the Motif style-binding Actions (Task 2). Both telnet
(``commands/motif.py``) and the web converge on ``action.run()``, mirroring
``SignatureViewSet`` (#1728 Task 4).
"""

from __future__ import annotations

from typing import Any

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from actions.definitions.motif_style import (
    BindMotifStyleAction,
    ListMotifStylesAction,
    UnbindMotifStyleAction,
)
from web.api.mixins import CharacterContextMixin
from world.items.models import Style
from world.magic.models import Resonance
from world.magic.serializers_motif_style import MotifStyleBindSerializer, MotifStyleUnbindSerializer
from world.magic.views_actor import PuppetActorMixin

#: Error detail returned when the request has no active character to act as.
NO_ACTIVE_CHARACTER_DETAIL = "No active character."
#: Error detail when an explicit X-Character-ID header doesn't resolve to one
#: of the requesting account's own characters (mirrors CharacterContextMixin
#: consumers such as PathIntentViewSet / CharacterGoalViewSet).
CHARACTER_NOT_FOUND_DETAIL = "No character found."
#: Error detail when the given style_id doesn't resolve to a catalog row.
STYLE_NOT_FOUND_DETAIL = "No such style."
#: Error detail when the given resonance_id doesn't resolve to a catalog row.
RESONANCE_NOT_FOUND_DETAIL = "No such resonance."


class MotifStyleViewSet(CharacterContextMixin, PuppetActorMixin, viewsets.ViewSet):
    """List, bind, and unbind the acting character's Motif style bindings.

    ``list`` runs :class:`ListMotifStylesAction`. ``bind``/``unbind`` resolve
    the ``Style`` (and, for ``bind``, the ``Resonance``) catalog rows, then
    dispatch :class:`BindMotifStyleAction` / :class:`UnbindMotifStyleAction`.

    Character scoping (#2030 review fix): a request carrying an
    ``X-Character-ID`` header is scoped to *that* character — validated as
    owned by the requesting account via ``CharacterContextMixin`` (the same
    header/ownership contract ``PathIntentViewSet``/``CharacterGoalViewSet``
    use) — so viewing a non-puppeted alt's sheet reads/writes that alt's
    bindings instead of silently acting as the currently puppeted character.
    A header naming a character the account doesn't own is rejected outright
    (404) rather than falling back to the puppet. No header at all preserves
    the original behavior: resolve the caller's active puppet.
    """

    permission_classes = [IsAuthenticated]

    def _resolve_scoped_actor(self, request: Any) -> tuple[Any, Response | None]:
        """Resolve the acting character for this request.

        Returns ``(actor, None)`` on success or ``(None, error_response)`` on
        failure. An explicit ``X-Character-ID`` header takes precedence (and
        must name an owned character, else 404); otherwise falls back to the
        caller's active puppet (400 if none).
        """
        if request.headers.get("X-Character-ID"):
            character = self._get_character(request)
            if character is None:
                return None, Response(
                    {"detail": CHARACTER_NOT_FOUND_DETAIL}, status=status.HTTP_404_NOT_FOUND
                )
            return character, None
        actor = self._resolve_actor(request)
        if actor is None:
            return None, Response(
                {"detail": NO_ACTIVE_CHARACTER_DETAIL}, status=status.HTTP_400_BAD_REQUEST
            )
        return actor, None

    def list(self, request: Any) -> Response:
        actor, error = self._resolve_scoped_actor(request)
        if error is not None:
            return error
        result = ListMotifStylesAction().run(actor=actor)
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result.data)

    @action(detail=False, methods=["post"], url_path="bind")
    def bind(self, request: Any) -> Response:
        serializer = MotifStyleBindSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor, error = self._resolve_scoped_actor(request)
        if error is not None:
            return error
        try:
            style = Style.objects.get(pk=serializer.validated_data["style_id"])
        except Style.DoesNotExist:
            return Response({"detail": STYLE_NOT_FOUND_DETAIL}, status=status.HTTP_400_BAD_REQUEST)
        try:
            resonance = Resonance.objects.get(pk=serializer.validated_data["resonance_id"])
        except Resonance.DoesNotExist:
            return Response(
                {"detail": RESONANCE_NOT_FOUND_DETAIL}, status=status.HTTP_400_BAD_REQUEST
            )
        result = BindMotifStyleAction().run(actor=actor, style=style, resonance=resonance)
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result.data)

    @action(detail=False, methods=["post"], url_path="unbind")
    def unbind(self, request: Any) -> Response:
        serializer = MotifStyleUnbindSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor, error = self._resolve_scoped_actor(request)
        if error is not None:
            return error
        try:
            style = Style.objects.get(pk=serializer.validated_data["style_id"])
        except Style.DoesNotExist:
            return Response({"detail": STYLE_NOT_FOUND_DETAIL}, status=status.HTTP_400_BAD_REQUEST)
        result = UnbindMotifStyleAction().run(actor=actor, style=style)
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result.data)
