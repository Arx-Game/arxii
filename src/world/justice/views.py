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

from world.justice.constants import CaseStatus
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


class WantedListView(_ViewerActionView):
    """GET /api/justice/wanted/?area=<id> — the public wanted board (#1826).

    Deliberately public-to-authenticated: crossing the wanted floor ends
    self-only visibility for those tiers. Tier + presented name + crime kinds;
    never raw values. An optional ``viewer`` adds two viewer-facing extras:
    ``viewer_can_pardon`` (the lord's-grant control gate, #1826) and the
    ``held`` list of awaiting-trial captives here (being held for trial is a
    public record — the discovery seam for the help-the-accused loop, #2378).
    """

    def get(self, request):
        from world.justice.lifecycle import can_pardon, wanted_rows_for_area  # noqa: PLC0415
        from world.justice.models import JusticeCase  # noqa: PLC0415

        area = self._area(request.query_params.get("area"))  # noqa: USE_FILTERSET — single lookup param
        if area is None:
            return Response({"detail": "Unknown area."}, status=400)
        viewer = self._viewer_persona(request)
        held = [
            {"case_id": case.pk, "persona_name": case.persona.name}
            for case in JusticeCase.objects.filter(
                area=area, status=CaseStatus.AWAITING_TRIAL
            ).select_related("persona")
        ]
        return Response(
            {
                "wanted": wanted_rows_for_area(area),
                "held": held,
                "viewer_can_pardon": viewer is not None and can_pardon(viewer, area),
            }
        )


class MyCaseView(_ViewerActionView):
    """GET /api/justice/my-case/?viewer= — the captive's own case picture (#2378)."""

    def get(self, request):
        from world.justice.models import JusticeCase  # noqa: PLC0415
        from world.justice.pipeline import (  # noqa: PLC0415
            exculpatory_total,
            release_threshold,
        )

        persona = self._viewer_persona(request)
        if persona is None:
            return Response({"detail": "Unknown viewer."}, status=400)
        case = (
            JusticeCase.objects.filter(persona=persona, status="awaiting_trial")
            .select_related("area", "society")
            .first()
        )
        if case is None:
            return Response({"case": None})
        return Response(
            {
                "case": {
                    "id": case.pk,
                    "area_name": case.area.name,
                    "society_name": case.society.name,
                    "opened_at": case.opened_at,
                    "evidence_total": exculpatory_total(case),
                    "release_threshold": release_threshold(case),
                    "failed_outs": case.failed_outs,
                }
            }
        )


class SubmitEvidenceView(_ViewerActionView):
    """POST /api/justice/cases/evidence/ — help the accused; never hurt (#2378)."""

    def post(self, request):
        from world.justice.models import JusticeCase  # noqa: PLC0415
        from world.justice.pipeline import (  # noqa: PLC0415
            JusticePipelineError,
            exculpatory_total,
            submit_exculpatory,
        )

        persona = self._viewer_persona(request)
        raw_case = request.data.get("case")
        case = (
            JusticeCase.objects.filter(pk=int(raw_case)).first()
            if raw_case is not None and str(raw_case).isdigit()
            else None
        )
        if persona is None or case is None:
            return Response({"detail": "Unknown viewer or case."}, status=400)
        manufactured = bool(request.data.get("manufactured"))
        try:
            submit_exculpatory(case, persona, manufactured=manufactured)
        except JusticePipelineError as exc:
            return Response({"detail": exc.user_message}, status=400)
        case.refresh_from_db()
        return Response(
            {"status": case.status, "evidence_total": exculpatory_total(case)},
            status=201,
        )


class InitiateTrialView(_ViewerActionView):
    """POST /api/justice/cases/trial/ — the captive calls their moment (#2378)."""

    def post(self, request):
        from world.justice.models import JusticeCase  # noqa: PLC0415
        from world.justice.pipeline import (  # noqa: PLC0415
            JusticePipelineError,
            initiate_trial,
        )
        from world.scenes.models import Persona  # noqa: PLC0415

        persona = self._viewer_persona(request)
        raw_case = request.data.get("case")
        case = (
            JusticeCase.objects.filter(pk=int(raw_case)).first()
            if raw_case is not None and str(raw_case).isdigit()
            else None
        )
        if persona is None or case is None:
            return Response({"detail": "Unknown viewer or case."}, status=400)
        helper_ids = request.data.get("helpers") or []
        helpers = list(
            Persona.objects.filter(pk__in=[int(h) for h in helper_ids if str(h).isdigit()])
        )
        try:
            case = initiate_trial(case, persona, helpers)
        except JusticePipelineError as exc:
            return Response({"detail": exc.user_message}, status=400)
        return Response(
            {
                "verdict": case.verdict,
                "sentence_kind": case.sentence_kind,
                "sentence_amount": case.sentence_amount,
            }
        )
