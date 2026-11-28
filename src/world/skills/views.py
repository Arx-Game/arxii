"""
Skills API views.
"""

from django.db.models import Prefetch
from django.http import Http404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from actions.constants import ActionBackend
from actions.player_interface import dispatch_player_action
from actions.types import ActionRef
from world.action_points.models import ActionPointConfig
from world.skills.filters import SkillFilter, SpecializationFilter
from world.skills.mentoring import answerable_allocation_ids, mentoring_for_account
from world.skills.models import (
    PathSkillSuggestion,
    Skill,
    SkillPointBudget,
    Specialization,
    TrainingAllocation,
)
from world.skills.serializers import (
    PathSkillSuggestionSerializer,
    SkillListSerializer,
    SkillPointBudgetSerializer,
    SkillSerializer,
    SpecializationSerializer,
)
from world.skills.serializers.training import (
    ManageTrainingAddSerializer,
    ManageTrainingUpdateSerializer,
    MentoringListSerializer,
    TrainingAllocationSerializer,
)
from world.skills.services import training_teaching_context

_NO_PUPPET_MESSAGE = "You must be playing a character to manage training."

_OPERATION_ADD = "add"
_OPERATION_UPDATE = "update"
_OPERATION_REMOVE = "remove"
_AP_AMOUNT_KEY = "ap_amount"
_MENTOR_PERSONA_ID_KEY = "mentor_persona_id"


class TrainingAllocationListSerializer(serializers.Serializer):
    """Schema wrapper for the training allocation list response."""

    allocations = TrainingAllocationSerializer(many=True)
    remaining_weekly_budget = serializers.IntegerField()


class SkillViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for listing skills and their specializations.

    list: Get all active skills (lighter serializer without specializations)
    retrieve: Get a single skill with its specializations
    """

    permission_classes = [IsAuthenticated]
    pagination_class = None  # Only 16 skills, no pagination needed
    filter_backends = [DjangoFilterBackend]
    filterset_class = SkillFilter

    def get_queryset(self):
        """Return skills ordered by display_order."""
        return (
            Skill.objects.all()
            .prefetch_related(
                Prefetch(
                    "specializations",
                    queryset=Specialization.objects.all(),
                    to_attr="cached_specializations",
                ),
            )
            .order_by("display_order")
        )

    def get_serializer_class(self):
        """Use lighter serializer for list, full serializer for detail."""
        if self.action == "list":
            return SkillListSerializer
        return SkillSerializer

    @action(detail=False, methods=["get"])  # type: ignore[arg-type]
    def with_specializations(self, request):
        """
        Get all skills with their specializations in one request.

        This is useful for CG where we need all skills and specs upfront.
        """
        queryset = self.get_queryset()
        serializer = SkillSerializer(queryset, many=True)
        return Response(serializer.data)


class SpecializationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for listing specializations.

    Can filter by parent_skill to get specializations for a specific skill.
    """

    serializer_class = SpecializationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # ~72 specializations, typically filtered by parent_skill
    filter_backends = [DjangoFilterBackend]
    filterset_class = SpecializationFilter

    def get_queryset(self):
        """Return specializations ordered by parent skill and display_order."""
        return Specialization.objects.select_related("parent_skill").order_by(
            "parent_skill__display_order", "display_order"
        )


class PathSkillSuggestionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for path skill suggestions.

    Filter by character_path to get suggestions for a specific path.
    """

    serializer_class = PathSkillSuggestionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # Small dataset, typically ~5 suggestions per path
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["character_path"]

    def get_queryset(self):
        """Return suggestions ordered by display_order."""
        return PathSkillSuggestion.objects.select_related("character_path", "skill").order_by(
            "character_path", "display_order"
        )


class SkillPointBudgetViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for skill point budget configuration.

    This is a single-row configuration model.
    """

    serializer_class = SkillPointBudgetSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # Single-row configuration model

    def get_queryset(self):
        """Return the active budget (single row)."""
        return SkillPointBudget.objects.all()

    def list(self, request, *args, **kwargs):
        """Override list to return the single budget directly, not as array."""
        budget = SkillPointBudget.get_active_budget()
        serializer = self.get_serializer(budget)
        return Response(serializer.data)


class TrainingAllocationViewSet(viewsets.ViewSet):
    """Manage weekly training allocations for the active character.

    All writes dispatch through ``ManageTrainingAction`` (key ``manage_training``)
    so telnet and web share the same mutation path.
    """

    permission_classes = [IsAuthenticated]
    pagination_class = None  # Character-scoped list; small enough to return in full
    filter_backends = []  # No additional filtering on this character-scoped endpoint

    def _active_puppet(self, request):
        """Return the played character, or raise a validation error if absent.

        Never ``request.user.puppet``: under ``MULTISESSION_MODE = 3`` that
        property is a list, not a single object (see
        ``missions.views._acting_character``), which is how this endpoint
        500'd in production with ``AttributeError: 'list' object has no
        attribute 'pk'`` (#3935, same class as Sentry ARX2-7).
        ``character_for_request`` reads the account's durable selection
        instead.
        """
        from world.roster.services.selection import character_for_request  # noqa: PLC0415

        puppet = character_for_request(request, entry_id=None)
        if puppet is None:
            raise serializers.ValidationError(_NO_PUPPET_MESSAGE)
        return puppet

    _MISSING_PK_MESSAGE = "A training allocation id is required."

    def _dispatch_manage_training(self, puppet, kwargs):
        """Dispatch a ``manage_training`` action for the puppet."""
        ref = ActionRef(backend=ActionBackend.REGISTRY, registry_key="manage_training")
        return dispatch_player_action(puppet, ref, kwargs)

    def _allocation_id(self, pk):
        """Return ``pk`` as an int, or raise if it's missing."""
        if pk is None:
            raise serializers.ValidationError(self._MISSING_PK_MESSAGE)
        return int(pk)

    @extend_schema(responses={200: TrainingAllocationListSerializer})
    def list(self, request, *args, **kwargs):
        """Return all allocations for the active character plus remaining budget."""
        puppet = self._active_puppet(request)
        allocations = list(
            TrainingAllocation.objects.filter(character_id=puppet.pk)
            .select_related(
                "character",
                "skill",
                "specialization__parent_skill",
                "mentor__character_sheet__character",
            )
            .prefetch_related(
                Prefetch(
                    "skill__specializations",
                    queryset=Specialization.objects.all(),
                    to_attr="cached_specializations",
                ),
            )
        )
        total = sum(allocation.ap_amount for allocation in allocations)
        remaining = max(0, ActionPointConfig.get_weekly_regen() - total)
        serializer = TrainingAllocationSerializer(
            allocations,
            many=True,
            context={
                "request": request,
                "remaining_weekly_budget": remaining,
                "teaching_context": training_teaching_context(allocations),
            },
        )
        return Response({"allocations": serializer.data, "remaining_weekly_budget": remaining})

    @extend_schema(
        request=ManageTrainingAddSerializer,
        responses={201: TrainingAllocationSerializer},
    )
    def create(self, request):
        """Create a new training allocation for the active character."""
        puppet = self._active_puppet(request)
        serializer = ManageTrainingAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        kwargs = {"operation": _OPERATION_ADD, **serializer.validated_data}
        result = self._dispatch_manage_training(puppet, kwargs)
        if not result.detail.success:
            raise serializers.ValidationError(result.detail.message)

        allocation = TrainingAllocation.objects.get(pk=result.detail.data["allocation_id"])
        read_serializer = TrainingAllocationSerializer(
            allocation,
            context={
                "request": request,
                "teaching_context": training_teaching_context([allocation]),
            },
        )
        return Response(read_serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=ManageTrainingUpdateSerializer,
        responses={200: TrainingAllocationSerializer},
    )
    def partial_update(self, request, pk=None):
        """Update an existing training allocation owned by the active character."""
        puppet = self._active_puppet(request)
        serializer = ManageTrainingUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        kwargs: dict[str, object] = {
            "operation": _OPERATION_UPDATE,
            "allocation_id": self._allocation_id(pk),
        }
        if _AP_AMOUNT_KEY in serializer.validated_data:
            kwargs[_AP_AMOUNT_KEY] = serializer.validated_data[_AP_AMOUNT_KEY]
        if _MENTOR_PERSONA_ID_KEY in serializer.validated_data:
            kwargs[_MENTOR_PERSONA_ID_KEY] = serializer.validated_data[_MENTOR_PERSONA_ID_KEY]

        result = self._dispatch_manage_training(puppet, kwargs)
        if not result.detail.success:
            raise serializers.ValidationError(result.detail.message)

        allocation = TrainingAllocation.objects.get(pk=pk)
        read_serializer = TrainingAllocationSerializer(
            allocation,
            context={
                "request": request,
                "teaching_context": training_teaching_context([allocation]),
            },
        )
        return Response(read_serializer.data)

    @extend_schema(responses={204: None})
    def destroy(self, request, pk=None):
        """Remove a training allocation owned by the active character."""
        puppet = self._active_puppet(request)
        kwargs = {
            "operation": _OPERATION_REMOVE,
            "allocation_id": self._allocation_id(pk),
        }
        result = self._dispatch_manage_training(puppet, kwargs)
        if not result.detail.success:
            raise serializers.ValidationError(result.detail.message)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(responses={200: MentoringListSerializer})
    @action(detail=False, methods=["get"], url_path="mentoring")  # type: ignore[arg-type]
    def mentoring(self, request):
        """Every request waiting on the requester's answer and every student she teaches.

        The list belongs to the account: it holds the allocations of every character the
        account may answer for, a game master's held NPC included (#5326). It is scoped by the
        requester, never by a selected character.
        """
        return Response(MentoringListSerializer(mentoring_for_account(request.user)).data)

    def _answer_mentoring(self, request, pk, answer):
        """Answer one mentoring request through ``AnswerMentoringAction`` (#5326).

        An id the requester may not answer for is a 404, so nothing says whether the row
        exists. A refusal is a 400 whose body is the sentence the action returns.
        """
        from actions.definitions.progression import AnswerMentoringAction  # noqa: PLC0415

        if pk is None or not str(pk).isdigit():
            raise Http404
        allocation = (
            TrainingAllocation.objects.filter(pk=int(pk), mentor__isnull=False)
            .select_related("character", "mentor")
            .first()
        )
        if allocation is None or allocation.pk not in answerable_allocation_ids(
            request.user, [allocation]
        ):
            raise Http404
        result = AnswerMentoringAction().run(
            actor=None, account=request.user, answer=answer, allocation_id=allocation.pk
        )
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": result.message})

    @extend_schema(request=None, responses={200: None})
    @action(detail=True, methods=["post"], url_path="accept-mentoring")  # type: ignore[arg-type]
    def accept_mentoring(self, request, pk=None):
        """The mentor agrees to teach: the training counts as mentored from now."""
        return self._answer_mentoring(request, pk, "accept")

    @extend_schema(request=None, responses={200: None})
    @action(detail=True, methods=["post"], url_path="decline-mentoring")  # type: ignore[arg-type]
    def decline_mentoring(self, request, pk=None):
        """The mentor declines: the mentor is cleared from the allocation."""
        return self._answer_mentoring(request, pk, "decline")

    @extend_schema(request=None, responses={200: None})
    @action(detail=True, methods=["post"], url_path="stop-mentoring")  # type: ignore[arg-type]
    def stop_mentoring(self, request, pk=None):
        """The mentor stops teaching: the mentor and the agreement are cleared."""
        return self._answer_mentoring(request, pk, "stop")
