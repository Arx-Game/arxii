"""The scene GM's live answer panel API (#4333 slice 5).

Lists the requester's own pending ``BEING_ANSWER`` prompts that a rite in their
scene raised (staff: any), and sends or dismisses one. The ``answer`` and
``dismiss`` actions dispatch the registry actions, which own the addressed-GM gate.
"""

from __future__ import annotations

from django.db.models import QuerySet
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
from world.worship.live_serializers import LivePromptSerializer, LiveSendSerializer
from world.worship.steward_serializers import StewardActionResultSerializer


class LivePromptViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Rites waiting on a scene GM's live answer: the answer panel."""

    serializer_class = LivePromptSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["scene"]

    queryset = GMPrompt.objects.none()  # the schema's model; get_queryset scopes it

    def get_queryset(self) -> QuerySet[GMPrompt]:
        prompts = GMPrompt.objects.filter(
            kind=GMPromptKind.BEING_ANSWER,
            status=GMPromptStatus.PENDING,
            rite_performance__isnull=False,
        )
        if not self.request.user.is_staff:
            prompts = prompts.filter(addressed_to=self.request.user)
        return prompts.select_related(
            "rite_performance__rite__being",
            "rite_performance__outcome_tier",
            "rite_performance__character_sheet",
            "subject_persona",
            "character_sheet",
        ).order_by("created_at", "pk")

    @extend_schema(request=LiveSendSerializer, responses=StewardActionResultSerializer)
    @action(detail=True, methods=["post"])
    def answer(self, request: Request, pk: str | None = None) -> Response:
        """Send one of the being's answers, or one of its miracles."""
        from actions.definitions.worship import AnswerBeingPromptAction  # noqa: PLC0415

        prompt = self.get_object()
        body = LiveSendSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        result = AnswerBeingPromptAction().run(
            actor=None,
            account=request.user,
            prompt_id=prompt.pk,
            answer_id=data.get("answer"),
            miracle_id=data.get("miracle"),
            text=data.get("text", ""),
        )
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": result.message})

    @extend_schema(request=None, responses=StewardActionResultSerializer)
    @action(detail=True, methods=["post"])
    def dismiss(self, request: Request, pk: str | None = None) -> Response:
        """Dismiss: nothing is sent."""
        from actions.definitions.dramatic_moments import DismissGMPromptAction  # noqa: PLC0415

        prompt = self.get_object()
        result = DismissGMPromptAction().run(actor=None, account=request.user, prompt_id=prompt.pk)
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Dismissed. Nothing was sent."})
