"""The table page's Beings section API (#4333 slice 4).

A stewarded being's table GM (or staff) reads the being's card, writes its
pledge types, answers and sacrifice lines, and answers its closed pledges.
Every queryset is scoped to the beings the requester may author
(``stewarded_beings_for``); the ``answer`` and ``dismiss`` actions dispatch the
registry actions, which own the addressed-GM gate.
"""

from __future__ import annotations

from django.db.models import QuerySet
from django_filters import rest_framework as filters
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from world.gm.constants import GMPromptKind, GMPromptStatus
from world.gm.models import GMPrompt
from world.stories.pagination import StandardResultsSetPagination
from world.worship.models import Answer, AnswerSacrificeLine, Pledge, WorshippedBeing
from world.worship.steward_serializers import (
    StewardActionResultSerializer,
    StewardAnswerRequestSerializer,
    StewardAnswerSerializer,
    StewardedBeingSerializer,
    StewardPledgeSerializer,
    StewardPromptSerializer,
    StewardSacrificeLineSerializer,
)
from world.worship.steward_services import stewarded_beings_for


class StewardedBeingFilter(filters.FilterSet):
    table = filters.NumberFilter(field_name="steward__table")

    class Meta:
        model = WorshippedBeing
        fields = ["table"]


class StewardedBeingViewSet(viewsets.ReadOnlyModelViewSet):
    """The beings a table stewards, as the Beings section's cards."""

    serializer_class = StewardedBeingSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = StewardedBeingFilter

    def get_queryset(self) -> QuerySet[WorshippedBeing]:
        return stewarded_beings_for(self.request.user)


class StewardPledgeViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """A stewarded being's pledge types. Retired by clearing Active, never deleted:
    a taken pledge keeps pointing at its type."""

    serializer_class = StewardPledgeSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["being"]

    def get_queryset(self) -> QuerySet[Pledge]:
        return (
            Pledge.objects.filter(being__in=stewarded_beings_for(self.request.user))
            .select_related("being")
            .order_by("being__name", "name")
        )


class StewardAnswerViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """A stewarded being's answers. Retired by clearing Active, never deleted: a
    delivered vision keeps its answer."""

    serializer_class = StewardAnswerSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["being", "pledge", "outcome_tier"]

    def get_queryset(self) -> QuerySet[Answer]:
        return (
            Answer.objects.filter(being__in=stewarded_beings_for(self.request.user))
            .select_related("outcome_tier")
            .order_by("being__name", "-outcome_tier__success_level", "pk")
        )


class StewardSacrificeLineViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """An answer's lines for its being's favored facets."""

    serializer_class = StewardSacrificeLineSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["answer"]

    def get_queryset(self) -> QuerySet[AnswerSacrificeLine]:
        return (
            AnswerSacrificeLine.objects.filter(
                answer__being__in=stewarded_beings_for(self.request.user)
            )
            .select_related("facet")
            .order_by("answer", "facet__name")
        )


class StewardPromptFilter(filters.FilterSet):
    table = filters.NumberFilter(field_name="pledge__pledge__being__steward__table")

    class Meta:
        model = GMPrompt
        fields = ["table"]


class StewardPromptViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Closed pledges waiting on their being's steward: the answer panel.

    Lists the requester's own pending ``BEING_ANSWER`` prompts (staff: any, so
    staff can cover for an absent GM through the same panel).
    """

    serializer_class = StewardPromptSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = StewardPromptFilter

    def get_queryset(self) -> QuerySet[GMPrompt]:
        prompts = GMPrompt.objects.filter(
            kind=GMPromptKind.BEING_ANSWER,
            status=GMPromptStatus.PENDING,
            pledge__isnull=False,
        )
        if not self.request.user.is_staff:
            prompts = prompts.filter(addressed_to=self.request.user)
        return prompts.select_related(
            "pledge__pledge__being__steward",
            "pledge__prayer",
            "pledge__closing_performance__outcome_tier",
            "subject_persona",
            "character_sheet",
        ).order_by("created_at", "pk")

    @extend_schema(request=StewardAnswerRequestSerializer, responses=StewardActionResultSerializer)
    @action(detail=True, methods=["post"])
    def answer(self, request: Request, pk: str | None = None) -> Response:
        """Send one of the being's answers, or the GM's own text with a clue."""
        from actions.definitions.worship import AnswerBeingPromptAction  # noqa: PLC0415

        prompt = self.get_object()
        body = StewardAnswerRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        result = AnswerBeingPromptAction().run(
            actor=None,
            account=request.user,
            prompt_id=prompt.pk,
            answer_id=data.get("answer"),
            text=data.get("text", ""),
            clue_id=data.get("clue"),
        )
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": result.message})

    @extend_schema(request=None, responses=StewardActionResultSerializer)
    @action(detail=True, methods=["post"])
    def dismiss(self, request: Request, pk: str | None = None) -> Response:
        """Dismiss: the being's authored answers are drawn instead."""
        from actions.definitions.dramatic_moments import DismissGMPromptAction  # noqa: PLC0415

        prompt = self.get_object()
        result = DismissGMPromptAction().run(actor=None, account=request.user, prompt_id=prompt.pk)
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Dismissed. An authored answer was drawn."})
