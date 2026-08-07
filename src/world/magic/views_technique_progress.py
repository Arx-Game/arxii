"""Technique progress meter API views (#2739 Task 2).

Web DRF surface over ``TrainTechniqueAction`` (#2739 Task 1) — telnet's
``train`` command and this endpoint converge on ``action.run()``, mirroring
``MotifStyleViewSet`` (#2030) for character scoping.
"""

from __future__ import annotations

from typing import Any

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from actions.definitions.technique_training import TrainTechniqueAction
from web.api.mixins import CharacterContextMixin
from world.game_clock.week_services import get_current_game_week
from world.magic.models import TechniqueProgress, TechniqueProgressWeekly
from world.magic.serializers import TechniqueProgressSerializer, TrainTechniqueRequestSerializer
from world.magic.services.gift_acquisition import get_gift_acquisition_config
from world.magic.views_actor import PuppetActorMixin

#: Error detail returned when the request has no active character to act as.
NO_ACTIVE_CHARACTER_DETAIL = "No active character."
#: Error detail when an explicit X-Character-ID header doesn't resolve to one
#: of the requesting account's own characters (mirrors CharacterContextMixin
#: consumers such as MotifStyleViewSet/PathIntentViewSet/CharacterGoalViewSet).
CHARACTER_NOT_FOUND_DETAIL = "No character found."
#: Error detail when the ``<id>`` path segment on the ``train`` action isn't a
#: technique pk at all (never surfaced by a well-formed frontend request).
TECHNIQUE_NOT_FOUND_DETAIL = "No such technique."


class TechniqueProgressViewSet(CharacterContextMixin, PuppetActorMixin, viewsets.ViewSet):
    """List the acting character's technique-progress meters; train one via POST.

    ``list`` returns the scoped character's own ``TechniqueProgress`` rows —
    another account's meters are never visible. ``POST <technique_id>/train/``
    dispatches :class:`TrainTechniqueAction` (#2739 Task 1); the ``<id>`` path
    segment is the ``Technique`` pk (matching the action's own ``technique_id``
    kwarg), not the ``TechniqueProgress`` row's pk, so a technique with no
    meter yet cleanly surfaces the action's own "you aren't training that"
    failure as a 400 rather than a router-level 404.

    Character scoping mirrors ``MotifStyleViewSet`` (#2030): an
    ``X-Character-ID`` header, once validated as owned via
    ``CharacterContextMixin``, takes precedence over the caller's active
    puppet; no header falls back to the puppet (400 if none); a header
    naming an unowned character 404s rather than silently falling back.
    """

    permission_classes = [IsAuthenticated]

    def _resolve_scoped_actor(self, request: Any) -> tuple[Any, Response | None]:
        """Resolve the acting character for this request.

        Returns ``(actor, None)`` on success or ``(None, error_response)`` on
        failure. Mirrors ``MotifStyleViewSet._resolve_scoped_actor``.
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
        # RoomProfile/CharacterSheet share ObjectDB's pk (both primary_key=True
        # O2Os onto it) — filter directly off the puppet's pk, no extra fetch.
        rows = list(
            TechniqueProgress.objects.filter(character_sheet_id=actor.pk)
            .select_related(
                "technique",
                # FK chain consumed by TechniqueProgressSerializer.teacher_name
                # (RosterTenure.display_name walks roster_entry → character_sheet
                # → character; mirrors ThreadWeavingTeachingOfferViewSet).
                "teacher_tenure__roster_entry__character_sheet__character",
            )
            .order_by("technique__name")
        )
        serializer = TechniqueProgressSerializer(
            rows,
            many=True,
            context={"weekly_remaining_by_technique_id": self._weekly_remaining(actor, rows)},
        )
        return Response(serializer.data)

    @staticmethod
    def _weekly_remaining(actor: Any, rows: list[TechniqueProgress]) -> dict[int, int]:
        """Batch-compute remaining weekly training points per technique.

        One ``GameWeek`` lookup, one config lookup (both cached singletons),
        and one batched query over the listed meters' technique ids — never
        per-row, so this stays cheap regardless of how many meters a
        character has open. ``TechniqueProgressSerializer.get_weekly_remaining``
        degrades to ``None`` when this mapping is absent.
        """
        if not rows:
            return {}
        game_week = get_current_game_week()
        config = get_gift_acquisition_config()
        contributed = dict(
            TechniqueProgressWeekly.objects.filter(
                character_sheet_id=actor.pk,
                game_week=game_week,
                technique_id__in=[row.technique_id for row in rows],
            ).values_list("technique_id", "points_contributed")
        )
        remaining: dict[int, int] = {}
        for row in rows:
            cap = config.weekly_training_cap
            if row.is_cross_path and config.cross_path_cap_divisor > 1:
                cap = config.weekly_training_cap // config.cross_path_cap_divisor
            remaining[row.technique_id] = max(0, cap - contributed.get(row.technique_id, 0))
        return remaining

    @action(detail=True, methods=["post"], url_path="train")
    def train(self, request: Any, pk: str | None = None) -> Response:
        actor, error = self._resolve_scoped_actor(request)
        if error is not None:
            return error
        serializer = TrainTechniqueRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            technique_id = int(pk)
        except (TypeError, ValueError):
            return Response(
                {"detail": TECHNIQUE_NOT_FOUND_DETAIL}, status=status.HTTP_400_BAD_REQUEST
            )
        result = TrainTechniqueAction().run(
            actor=actor,
            technique_id=technique_id,
            ap_to_invest=serializer.validated_data.get("ap_to_invest"),
        )
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result.data)
