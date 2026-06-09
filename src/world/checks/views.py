"""ViewSet for ConsequenceOutcome read API."""

from __future__ import annotations

from django.db.models import Prefetch, QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ReadOnlyModelViewSet

from actions.models.consequence_pools import ConsequencePoolEntry
from world.checks.filters import ConsequenceOutcomeFilter
from world.checks.outcome_models import ConsequenceOutcome, ConsequenceOutcomeModifier
from world.checks.serializers import ConsequenceOutcomeSerializer
from world.stories.pagination import StandardResultsSetPagination

# Prefetch querysets reused across list and retrieve.
_POOL_ENTRIES_PREFETCH = Prefetch(
    "pool__entries",
    queryset=ConsequencePoolEntry.objects.select_related("consequence"),
)
_PARENT_ENTRIES_PREFETCH = Prefetch(
    "pool__parent__entries",
    queryset=ConsequencePoolEntry.objects.select_related("consequence"),
)
_MODIFIERS_PREFETCH = Prefetch(
    "modifiers",
    queryset=ConsequenceOutcomeModifier.objects.all(),
)


class ConsequenceOutcomeViewSet(ReadOnlyModelViewSet):
    """Read-only endpoint for ConsequenceOutcome records.

    Returns the roulette display recomputed from the persisted pool +
    selected_consequence on every read.  Authenticated users may read any
    record (list is all-records; no server-side ownership scoping because
    staff need the full list and the frontend scopes by character via the
    ``character`` filter).

    Write operations are intentionally absent — outcomes are append-only and
    written by the resolution pipeline.
    """

    serializer_class = ConsequenceOutcomeSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = ConsequenceOutcomeFilter
    pagination_class = StandardResultsSetPagination

    def get_permissions(self) -> list:
        return [IsAuthenticated()]

    def get_queryset(self) -> QuerySet[ConsequenceOutcome]:
        return (
            ConsequenceOutcome.objects.select_related(
                "pool",
                "pool__parent",
                "selected_consequence",
                "character",
                "check_type",
            )
            .prefetch_related(
                _MODIFIERS_PREFETCH,
                _POOL_ENTRIES_PREFETCH,
                _PARENT_ENTRIES_PREFETCH,
            )
            .order_by("-created_at")
        )
