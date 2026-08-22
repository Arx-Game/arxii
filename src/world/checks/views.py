"""ViewSet for ConsequenceOutcome read API."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Prefetch, Q, QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ReadOnlyModelViewSet

from actions.models.consequence_pools import ConsequencePoolEntry
from world.checks.catalog_invocation import catalog_queryset
from world.checks.constants import CheckCallTargetStatus
from world.checks.filters import CheckTypeFilter, ConsequenceOutcomeFilter
from world.checks.models import CheckCallTarget, CheckType, CheckTypeTrait
from world.checks.outcome_models import ConsequenceOutcome, ConsequenceOutcomeModifier
from world.checks.serializers import (
    CheckCallTargetSerializer,
    CheckTypeSerializer,
    ConsequenceOutcomeSerializer,
)
from world.gm.permissions import IsGMOrStaff
from world.mechanics.models import ApproachConsequence, ChallengeTemplateConsequence
from world.stories.pagination import StandardResultsSetPagination

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet

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


class CheckTypeViewSet(ReadOnlyModelViewSet):
    """Read-only GM catalog browse for CheckType (#3070) — the web sibling of
    telnet's ``gm check find``, feeding the web GM adjudication panel's Call
    Check picker.

    Scoped to staff/lore-authored, active rows only: ``owner_sheet__isnull``
    excludes the per-character synthesized magic check
    (``ensure_character_magic_check_type`` mints one row per ``CharacterSheet``;
    a player's own signature check has no place in a general catalog browse,
    mirroring the #2724 export-filter rationale on the model itself).
    Permission mirrors ``InvokeCatalogCheckAction``'s own gate in spirit
    (``IsGMOrStaff`` — the action's ``MinimumGMLevelPrerequisite(GMLevel.SENIOR)``
    is the real enforcement at invocation time; this endpoint only needs to keep
    the catalog out of non-GM hands, not re-derive the exact trust tier).
    """

    queryset = (
        CheckType.objects.filter(is_active=True, owner_sheet__isnull=True)
        .select_related("category")
        .prefetch_related(
            Prefetch(
                "traits",
                queryset=CheckTypeTrait.objects.select_related("trait").order_by("-weight"),
                to_attr="cached_traits",
            )
        )
        .order_by("category__display_order", "display_order", "name")
    )
    serializer_class = CheckTypeSerializer
    permission_classes = [IsGMOrStaff]
    filter_backends = [DjangoFilterBackend]
    filterset_class = CheckTypeFilter
    pagination_class = StandardResultsSetPagination


class PlayerCheckTypeViewSet(ReadOnlyModelViewSet):
    """Read-only catalog browse for the player-facing roll picker (#3295).

    Open to any authenticated player -- unlike ``CheckTypeViewSet`` (GM-only,
    staff-authored rows only), this is the "easy to find is the feature"
    discovery surface every player's own self-check roll picker uses. An
    optional ``character_id`` query param, when it resolves to a character the
    requesting account currently plays (validated the same way
    ``CanCreatePersonaInScene`` validates ownership), additionally surfaces
    that character's own synthesized magic ``CheckType`` row -- never another
    character's (``catalog_queryset``'s existing owner_sheet scope).
    """

    serializer_class = CheckTypeSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = CheckTypeFilter
    pagination_class = StandardResultsSetPagination

    def get_queryset(self) -> QuerySet[CheckType]:
        owner_sheet = self._owned_sheet()
        return (
            catalog_queryset(owner_sheet=owner_sheet)
            .select_related("category")
            .prefetch_related(
                Prefetch(
                    "traits",
                    queryset=CheckTypeTrait.objects.select_related("trait").order_by("-weight"),
                    to_attr="cached_traits",
                )
            )
            .order_by("category__display_order", "display_order", "name")
        )

    def _owned_sheet(self) -> CharacterSheet | None:
        # noqa: USE_FILTERSET -- this is ownership-validated queryset SCOPING (which
        # rows even exist to filter), not an optional client-toggleable filter a
        # FilterSet field can express as a pure narrowing lookup; it must run
        # unconditionally to keep other characters' synthesized rows excluded by
        # default, which a FilterSet's opt-in `method=` filter cannot guarantee.
        character_id = self.request.query_params.get("character_id")  # noqa: USE_FILTERSET
        if not character_id or not str(character_id).isdigit():
            return None
        played_ids = self.request.user.played_character_sheet_ids
        character_id = int(character_id)
        if character_id not in played_ids:
            return None
        from world.character_sheets.models import CharacterSheet  # noqa: PLC0415

        return CharacterSheet.objects.filter(pk=character_id).first()


class CheckCallTargetViewSet(ReadOnlyModelViewSet):
    """Read-only inbox of the requesting player's pending ``CheckCall`` prompts (#3295).

    Mirrors ``GMSummonOfferViewSet``'s shape: answer/decline are NOT DRF actions
    here -- they dispatch through the generic REGISTRY action-dispatch endpoint
    (``answer_check_call``/``decline_check_call``), the seam telnet's ``check
    answer``/``check decline`` also reaches.
    """

    serializer_class = CheckCallTargetSerializer
    queryset = CheckCallTarget.objects.none()
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self) -> QuerySet[CheckCallTarget]:
        played_ids = self.request.user.played_character_sheet_ids
        if not played_ids:
            return CheckCallTarget.objects.none()
        return (
            CheckCallTarget.objects.filter(
                target_sheet_id__in=played_ids,
                status=CheckCallTargetStatus.PENDING,
            )
            .select_related("call__check_type", "call__caller_persona")
            .order_by("-call__created_at")
        )


class ConsequenceOutcomeViewSet(ReadOnlyModelViewSet):
    """Read-only endpoint for ConsequenceOutcome records.

    Returns the roulette display recomputed on every read — from the persisted
    pool + selected_consequence, or, when pool is None (#865), reconstructed from
    the authored approach/template consequence links.

    Queryset scoping:
    - Staff users see all outcomes.
    - Non-staff users see outcomes for characters they own
      (chain: ConsequenceOutcome.character → CharacterSheet.character →
      ObjectDB.db_account == request.user), AND outcomes whose scene they
      participate in (#866) — reached via combat_interaction.scene or
      challenge_record.challenge_instance.situation_instance.scene.

    Write operations are intentionally absent — outcomes are append-only and
    written by the resolution pipeline.
    """

    serializer_class = ConsequenceOutcomeSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = ConsequenceOutcomeFilter
    pagination_class = StandardResultsSetPagination

    # drf-spectacular sets this to True on the view instance while generating
    # the schema. Declaring the default here keeps get_queryset's guard a plain
    # attribute read rather than a getattr with a literal name.
    swagger_fake_view = False

    def get_permissions(self) -> list:
        return [IsAuthenticated()]

    def get_queryset(self) -> QuerySet[ConsequenceOutcome]:
        # Schema generation must never reach the database, and carries no real
        # user — the scoping below read AnonymousUser.id and raised, so
        # drf-spectacular dropped this viewset and typed its path parameter as
        # "string". See the same guard on ConsequencePoolCatalogViewSet.
        if self.swagger_fake_view:
            return ConsequenceOutcome.objects.none()

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
        # Scope to outcomes for:
        # 1. The requesting user's own characters
        #    (chain: CharacterSheet.character (ObjectDB) → db_account == user).
        # 2. Any outcome anchored to a combat interaction in a scene the user
        #    participated in (combat_interaction.scene.participations.account == user).
        # 3. Any outcome anchored to a challenge record whose situation instance
        #    is linked to a scene the user participated in.
        return qs.filter(
            Q(character__character__db_account=user)
            | Q(combat_interaction__scene__participations__account=user)
            | Q(
                challenge_record__challenge_instance__situation_instance__scene__participations__account=user
            )
        ).distinct()
