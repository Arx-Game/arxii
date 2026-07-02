"""The justice web API (#1765) — the crime tab's read endpoint.

Self-only by construction (the #1765 leak table): the queryset is the
requesting account's own active persona's warrant rows — a ``viewer`` param
names which of the account's characters is viewing, validated through
``RosterEntry.objects.for_account`` so it can never reach another account's
heat, and IC scope resolves through ``active_persona_for_sheet`` (never
``primary_persona``). No public listing endpoint exists.
"""

from django.db.models import QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ReadOnlyModelViewSet

from world.justice.models import PersonaHeat
from world.justice.serializers import PersonaHeatSerializer
from world.roster.models import RosterEntry


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
