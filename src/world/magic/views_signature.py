"""Signature-bonus API views (#1728 Task 4).

Web DRF surface over the signature-bonus selection Actions (#1582). Both
telnet (``CmdSignature``) and the web converge on
``actions/definitions/signature.py`` via ``action.run()``, mirroring
``SanctumViewSet`` (#1497).
"""

from __future__ import annotations

from typing import Any

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from actions.definitions.signature import (
    SignatureClearAction,
    SignatureListAction,
    SignatureSetAction,
)
from world.magic.models import SignatureMotifBonus, Thread
from world.magic.serializers_signature import SignatureClearSerializer, SignatureSetSerializer
from world.magic.views_actor import PuppetActorMixin

#: Error detail returned when the request has no active character to act as.
NO_ACTIVE_CHARACTER_DETAIL = "No active character."
#: Error detail when the given thread_id isn't one of the actor's own threads.
THREAD_NOT_FOUND_DETAIL = "That is not one of your technique threads."
#: Error detail when the given bonus_id doesn't resolve to a catalog row.
BONUS_NOT_FOUND_DETAIL = "No such signature bonus."


class SignatureViewSet(PuppetActorMixin, viewsets.ViewSet):
    """List available bonuses and set/clear the signature bonus on a Thread.

    ``list`` runs :class:`SignatureListAction`. ``set``/``clear`` resolve the
    ``Thread`` (scoped to the actor's own threads) and, for ``set``, the
    ``SignatureMotifBonus`` catalog row, then dispatch
    :class:`SignatureSetAction` / :class:`SignatureClearAction`.
    """

    permission_classes = [IsAuthenticated]

    @staticmethod
    def _resolve_own_thread(actor: Any, thread_id: int) -> Thread | None:
        """Return the actor's own Thread matching ``thread_id``, or ``None``."""
        for thread in actor.threads.all():
            if thread.pk == thread_id:
                return thread
        return None

    def list(self, request: Any) -> Response:
        actor = self._resolve_actor(request)
        if actor is None:
            return Response(
                {"detail": NO_ACTIVE_CHARACTER_DETAIL}, status=status.HTTP_400_BAD_REQUEST
            )
        result = SignatureListAction().run(actor=actor)
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result.data)

    @action(detail=False, methods=["post"], url_path="set")
    def set_bonus(self, request: Any) -> Response:
        serializer = SignatureSetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = self._resolve_actor(request)
        if actor is None:
            return Response(
                {"detail": NO_ACTIVE_CHARACTER_DETAIL}, status=status.HTTP_400_BAD_REQUEST
            )
        thread = self._resolve_own_thread(actor, serializer.validated_data["thread_id"])
        if thread is None:
            return Response({"detail": THREAD_NOT_FOUND_DETAIL}, status=status.HTTP_400_BAD_REQUEST)
        try:
            bonus = SignatureMotifBonus.objects.get(pk=serializer.validated_data["bonus_id"])
        except SignatureMotifBonus.DoesNotExist:
            return Response({"detail": BONUS_NOT_FOUND_DETAIL}, status=status.HTTP_400_BAD_REQUEST)
        result = SignatureSetAction().run(actor=actor, thread=thread, bonus=bonus)
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result.data)

    @action(detail=False, methods=["post"], url_path="clear")
    def clear_bonus(self, request: Any) -> Response:
        serializer = SignatureClearSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = self._resolve_actor(request)
        if actor is None:
            return Response(
                {"detail": NO_ACTIVE_CHARACTER_DETAIL}, status=status.HTTP_400_BAD_REQUEST
            )
        thread = self._resolve_own_thread(actor, serializer.validated_data["thread_id"])
        if thread is None:
            return Response({"detail": THREAD_NOT_FOUND_DETAIL}, status=status.HTTP_400_BAD_REQUEST)
        result = SignatureClearAction().run(actor=actor, thread=thread)
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result.data)
