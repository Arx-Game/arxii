"""ViewSet for ConsequenceOutcome read API."""

from __future__ import annotations

from django.db.models import Prefetch, Q, QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ReadOnlyModelViewSet

from actions.models.consequence_pools import ConsequencePoolEntry
from world.checks.filters import ConsequenceOutcomeFilter
from world.checks.outcome_models import ConsequenceOutcome, ConsequenceOutcomeModifier
from world.checks.serializers import ConsequenceOutcomeSerializer
from world.mechanics.models import ApproachConsequence, ChallengeTemplateConsequence
from world.stories.pagination import StandardResultsSetPagination

# Prefetch pool entries including each consequence's outcome_tier so the
# serializer can read entry.consequence.outcome_tier.name from the cache
# without issuing additional queries.
_POOL_ENTRIES_PREFETCH = Prefetch(
    "pool__entries",
    queryset=ConsequencePoolEntry.objects.select_related("consequence__outcome_tier"),
)
_PARENT_ENTRIES_PREFETCH = Prefetch(
    "pool__parent__entries",
    queryset=ConsequencePoolEntry.objects.select_related("consequence__outcome_tier"),
)
_MODIFIERS_PREFETCH = Prefetch(
    "modifiers",
    queryset=ConsequenceOutcomeModifier.objects.all(),
)
# Prefetches for pool=None (challenge-based) outcomes: reconstruct roulette
# from authored ApproachConsequence and ChallengeTemplateConsequence links.
_APPROACH_CONSEQUENCES_PREFETCH = Prefetch(
    "challenge_record__approach__consequences",
    queryset=ApproachConsequence.objects.select_related("consequence__outcome_tier"),
)
_TEMPLATE_CONSEQUENCES_PREFETCH = Prefetch(
    "challenge_record__challenge_instance__template__challenge_consequences",
    queryset=ChallengeTemplateConsequence.objects.select_related("consequence__outcome_tier"),
)


class ConsequenceOutcomeViewSet(ReadOnlyModelViewSet):
    """Read-only endpoint for ConsequenceOutcome records.

    Returns the roulette display recomputed from the persisted pool +
    selected_consequence on every read.

    Queryset scoping:
    - Staff users see all outcomes.
    - Non-staff users see only outcomes for characters they own
      (chain: ConsequenceOutcome.character → CharacterSheet.character →
      ObjectDB.db_account == request.user).

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
        user = self.request.user
        qs = (
            ConsequenceOutcome.objects.select_related(
                "pool",
                "pool__parent",
                "selected_consequence__outcome_tier",
                "character",
                "check_type",
                "challenge_record__approach",
                "challenge_record__challenge_instance__template",
            )
            .prefetch_related(
                _MODIFIERS_PREFETCH,
                _POOL_ENTRIES_PREFETCH,
                _PARENT_ENTRIES_PREFETCH,
                _APPROACH_CONSEQUENCES_PREFETCH,
                _TEMPLATE_CONSEQUENCES_PREFETCH,
            )
            .order_by("-created_at")
        )
        if user.is_staff:
            return qs
        # Scope to outcomes for the requesting user's own characters.
        # Chain: CharacterSheet.character (ObjectDB) → db_account == user.
        return qs.filter(Q(character__character__db_account=user))
