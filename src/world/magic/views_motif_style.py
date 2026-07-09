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
from world.items.models import Style
from world.magic.models import Resonance
from world.magic.serializers_motif_style import MotifStyleBindSerializer, MotifStyleUnbindSerializer
from world.magic.views_actor import PuppetActorMixin

#: Error detail returned when the request has no active character to act as.
NO_ACTIVE_CHARACTER_DETAIL = "No active character."
#: Error detail when the given style_id doesn't resolve to a catalog row.
STYLE_NOT_FOUND_DETAIL = "No such style."
#: Error detail when the given resonance_id doesn't resolve to a catalog row.
RESONANCE_NOT_FOUND_DETAIL = "No such resonance."


class MotifStyleViewSet(PuppetActorMixin, viewsets.ViewSet):
    """List, bind, and unbind the actor's Motif style bindings.

    ``list`` runs :class:`ListMotifStylesAction`. ``bind``/``unbind`` resolve
    the ``Style`` (and, for ``bind``, the ``Resonance``) catalog rows, then
    dispatch :class:`BindMotifStyleAction` / :class:`UnbindMotifStyleAction`.
    """

    permission_classes = [IsAuthenticated]

    def list(self, request: Any) -> Response:
        actor = self._resolve_actor(request)
        if actor is None:
            return Response(
                {"detail": NO_ACTIVE_CHARACTER_DETAIL}, status=status.HTTP_400_BAD_REQUEST
            )
        result = ListMotifStylesAction().run(actor=actor)
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result.data)

    @action(detail=False, methods=["post"], url_path="bind")
    def bind(self, request: Any) -> Response:
        serializer = MotifStyleBindSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = self._resolve_actor(request)
        if actor is None:
            return Response(
                {"detail": NO_ACTIVE_CHARACTER_DETAIL}, status=status.HTTP_400_BAD_REQUEST
            )
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
        actor = self._resolve_actor(request)
        if actor is None:
            return Response(
                {"detail": NO_ACTIVE_CHARACTER_DETAIL}, status=status.HTTP_400_BAD_REQUEST
            )
        try:
            style = Style.objects.get(pk=serializer.validated_data["style_id"])
        except Style.DoesNotExist:
            return Response({"detail": STYLE_NOT_FOUND_DETAIL}, status=status.HTTP_400_BAD_REQUEST)
        result = UnbindMotifStyleAction().run(actor=actor, style=style)
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result.data)
