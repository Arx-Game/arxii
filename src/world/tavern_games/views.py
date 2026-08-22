"""Tavern games API (#3292).

``TavernGameViewSet`` is a read-only catalog browse (curated staff content,
authored via admin/fixtures - no player-facing CRUD). ``GameSessionViewSet``
is read-only for list/retrieve; every mutation dispatches the matching
REGISTRY action - the same seam the telnet ``game`` command uses - mirroring
``world.scenes.place_views.PlaceViewSet``.
"""

from __future__ import annotations

from http import HTTPMethod
from typing import TYPE_CHECKING

from django.db.models import Prefetch
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from world.tavern_games.filters import GameSessionFilterSet, TavernGameFilterSet
from world.tavern_games.models import GameSeat, GameSession, TavernGame
from world.tavern_games.serializers import GameSessionSerializer, TavernGameSerializer

if TYPE_CHECKING:
    from rest_framework.request import Request


class TavernGamesPagination(PageNumberPagination):
    page_size = 20


def _seats_prefetch() -> Prefetch:
    """``Prefetch`` for ``GameSession.seats`` into ``cached_seats``.

    The single source both ``GameSessionViewSet.queryset`` and
    ``_fetch_session_with_seats`` use, so ``GameSessionSerializer.get_seats``
    can read ``obj.cached_seats`` as plain attribute access, never a
    literal-string ``getattr`` fallback.
    """
    return Prefetch(
        "seats",
        queryset=GameSeat.objects.select_related("persona"),
        to_attr="cached_seats",
    )


def _fetch_session_with_seats(pk: int) -> GameSession:
    """Re-fetch a session by pk with ``cached_seats`` prefetched, for serialization."""
    return (
        GameSession.objects.select_related("game", "place", "opened_by")
        .prefetch_related(_seats_prefetch())
        .get(pk=pk)
    )


def _active_character(request: Request):
    """The requesting account's active-persona character, or None (#3292).

    Mirrors ``PlaceViewSet.join``/``.leave``: resolve every persona the
    account owns, then hand ``.run()`` the underlying ObjectDB character so
    the action itself resolves the active persona.
    """
    from world.scenes.interaction_permissions import get_account_personas  # noqa: PLC0415
    from world.scenes.models import Persona  # noqa: PLC0415

    persona_ids = get_account_personas(request)
    persona = Persona.objects.filter(pk__in=persona_ids).select_related("character_sheet").first()
    if persona is None:
        return None
    return persona.character_sheet.character


class TavernGameViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Read-only catalog of curated coin-stakes games."""

    queryset = TavernGame.objects.filter(is_active=True)
    serializer_class = TavernGameSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = TavernGamesPagination
    filterset_class = TavernGameFilterSet


class GameSessionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Read state; every write routes through the matching REGISTRY action."""

    queryset = GameSession.objects.select_related("game", "place", "opened_by").prefetch_related(
        _seats_prefetch()
    )
    serializer_class = GameSessionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = TavernGamesPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = GameSessionFilterSet

    def _dispatch(self, action_key: str, request: Request, **kwargs: object):
        """Run ``action_key`` as the account's active character.

        Returns ``(error_response, None)`` when no persona could be resolved,
        else ``(None, result)`` with the action's ``ActionResult``.
        """
        from actions.registry import get_action  # noqa: PLC0415

        character = _active_character(request)
        if character is None:
            error = Response(
                {"detail": "No personas found for your account."},
                status=status.HTTP_400_BAD_REQUEST,
            )
            return error, None
        result = get_action(action_key).run(actor=character, **kwargs)
        return None, result

    @action(detail=False, methods=[HTTPMethod.POST], url_path="open")
    def open(self, request: Request) -> Response:
        """Open a new table. Body: ``place``, ``game``, ``ante``."""
        from world.scenes.place_models import Place  # noqa: PLC0415

        place = Place.objects.filter(pk=request.data.get("place")).first()
        game = TavernGame.objects.filter(pk=request.data.get("game")).first()
        ante = request.data.get("ante")
        if place is None or game is None or ante is None:
            return Response(
                {"detail": "place, game, and ante are all required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        error, result = self._dispatch(
            "tavern_game_open", request, place=place, game=game, ante=ante
        )
        if error is not None:
            return error
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        session = _fetch_session_with_seats(result.data["session_id"])
        return Response(GameSessionSerializer(session).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=[HTTPMethod.POST], url_path="join")
    def join(self, request: Request, pk: int | None = None) -> Response:
        session = self.get_object()
        error, result = self._dispatch("tavern_game_join", request, session=session)
        if error is not None:
            return error
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        session = _fetch_session_with_seats(session.pk)
        return Response(GameSessionSerializer(session).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=[HTTPMethod.POST], url_path="roll")
    def roll(self, request: Request, pk: int | None = None) -> Response:
        session = self.get_object()
        error, result = self._dispatch("tavern_game_roll", request, session=session)
        if error is not None:
            return error
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        session = _fetch_session_with_seats(session.pk)
        return Response(GameSessionSerializer(session).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=[HTTPMethod.POST], url_path="leave")
    def leave(self, request: Request, pk: int | None = None) -> Response:
        session = self.get_object()
        error, result = self._dispatch("tavern_game_leave", request, session=session)
        if error is not None:
            return error
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        session = _fetch_session_with_seats(session.pk)
        return Response(GameSessionSerializer(session).data, status=status.HTTP_200_OK)
