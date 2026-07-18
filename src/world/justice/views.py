"""The justice web API (#1765) — the crime tab's read endpoint.

Self-only by construction (the #1765 leak table): the queryset is the
requesting account's own active persona's warrant rows — a ``viewer`` param
names which of the account's characters is viewing, validated through
``RosterEntry.objects.for_account`` so it can never reach another account's
heat, and IC scope resolves through ``active_persona_for_sheet`` (never
``primary_persona``). No public listing endpoint exists.
"""

from typing import TYPE_CHECKING

from django.db.models import QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ReadOnlyModelViewSet

from world.justice.models import PersonaHeat
from world.justice.serializers import PersonaHeatSerializer
from world.roster.models import RosterEntry

if TYPE_CHECKING:
    from world.areas.models import Area


class JusticePagination(PageNumberPagination):
    page_size = 50


class PersonaHeatViewSet(ReadOnlyModelViewSet):
    """The viewer's own pursuit picture — where they're wanted, and for what."""

    serializer_class = PersonaHeatSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = JusticePagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ("area",)

    def get_queryset(self) -> QuerySet[PersonaHeat]:
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        entry = self._viewer_entry()
        if entry is None:
            return PersonaHeat.objects.none()
        persona = active_persona_for_sheet(entry.character_sheet)
        if persona is None:
            return PersonaHeat.objects.none()
        # Bare-string prefetch (NOT Prefetch(to_attr=…)): PersonaHeat is a
        # SharedMemoryModel, and a to_attr list would persist on the cached
        # instance across requests (stale per-request data).
        return (
            PersonaHeat.objects.filter(persona=persona, value__gt=0)
            .select_related("area", "society")
            .prefetch_related("sources__deed")  # noqa: PREFETCH_STRING
        )

    def _viewer_entry(self) -> RosterEntry | None:
        """The active (viewing) character, validated as owned by the requester.

        Mirrors the secrets viewset (#1334): no (or an unowned) ``viewer`` → an
        empty queryset, never an account-wide aggregate.
        """
        raw = self.request.query_params.get("viewer")  # noqa: use_filterset — auth scope, not a filter
        if not raw or not raw.isdigit():
            return None
        return RosterEntry.objects.for_account(self.request.user).filter(pk=int(raw)).first()


class _ViewerActionView(APIView):
    """Shared viewer-resolution for the lifecycle actions (#1826).

    Same self-only contract as PersonaHeatViewSet: a ``viewer`` body/query
    param names one of the requester's own characters; IC scope resolves via
    ``active_persona_for_sheet``.
    """

    permission_classes = [IsAuthenticated]

    def _viewer_persona(self, request):
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        raw = request.data.get("viewer") or request.query_params.get(  # noqa: USE_FILTERSET — auth scope, not a filter
            "viewer"
        )
        if raw is None or not str(raw).isdigit():
            return None
        entry = RosterEntry.objects.for_account(request.user).filter(pk=int(raw)).first()
        if entry is None:
            return None
        return active_persona_for_sheet(entry.character_sheet)

    @staticmethod
    def _area(raw) -> "Area | None":
        from world.areas.models import Area  # noqa: PLC0415

        if raw is None or not str(raw).isdigit():
            return None
        return Area.objects.filter(pk=int(raw)).first()


class LieLowView(_ViewerActionView):
    """POST /api/justice/lie-low/ — declare or end going to ground (#1826)."""

    def post(self, request):
        from world.justice.lifecycle import (  # noqa: PLC0415
            HeatLifecycleError,
            declare_lie_low,
            end_lie_low,
        )

        persona = self._viewer_persona(request)
        area = self._area(request.data.get("area"))
        if persona is None or area is None:
            return Response({"detail": "Unknown viewer or area."}, status=400)
        if request.data.get("end"):
            state = end_lie_low(persona, area)
            return Response({"active": False, "was_active": state is not None})
        try:
            declare_lie_low(persona, area)
        except HeatLifecycleError as exc:
            return Response({"detail": exc.user_message}, status=400)
        return Response({"active": True}, status=201)


class BribeView(_ViewerActionView):
    """POST /api/justice/bribe/ — bribe the hunters in an area (#1826)."""

    def post(self, request):
        from world.justice.lifecycle import (  # noqa: PLC0415
            HeatLifecycleError,
            attempt_bribe,
            bribe_cost_for,
        )

        persona = self._viewer_persona(request)
        area = self._area(request.data.get("area"))
        if persona is None or area is None:
            return Response({"detail": "Unknown viewer or area."}, status=400)
        if request.data.get("preview"):
            return Response({"cost_coppers": bribe_cost_for(persona, area)})
        try:
            outcome = attempt_bribe(persona, area)
        except HeatLifecycleError as exc:
            return Response({"detail": exc.user_message}, status=400)
        return Response(outcome)


class PardonView(_ViewerActionView):
    """POST /api/justice/pardon/ — a lord's grant (#1826)."""

    def post(self, request):
        from world.justice.lifecycle import (  # noqa: PLC0415
            HeatLifecycleError,
            pardon_persona,
        )
        from world.scenes.models import Persona  # noqa: PLC0415

        granter = self._viewer_persona(request)
        area = self._area(request.data.get("area"))
        raw_target = request.data.get("target_persona")
        target = (
            Persona.objects.filter(pk=int(raw_target)).first()
            if raw_target is not None and str(raw_target).isdigit()
            else None
        )
        if granter is None or area is None or target is None:
            return Response({"detail": "Unknown viewer, target, or area."}, status=400)
        try:
            grant = pardon_persona(granter, target, area)
        except HeatLifecycleError as exc:
            return Response({"detail": exc.user_message}, status=400)
        return Response({"heat_cleared": grant.heat_cleared}, status=201)


class WantedListView(APIView):
    """GET /api/justice/wanted/?area=<id> — the public wanted board (#1826).

    Deliberately public-to-authenticated: crossing the wanted floor ends
    self-only visibility for those tiers. Tier + presented name + crime kinds;
    never raw values.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from world.areas.models import Area  # noqa: PLC0415
        from world.justice.lifecycle import wanted_rows_for_area  # noqa: PLC0415

        raw = request.query_params.get("area")  # noqa: USE_FILTERSET — single lookup param
        if raw is None or not str(raw).isdigit():
            return Response({"detail": "Unknown area."}, status=400)
        area = Area.objects.filter(pk=int(raw)).first()
        if area is None:
            return Response({"detail": "Unknown area."}, status=400)
        return Response({"wanted": wanted_rows_for_area(area)})
