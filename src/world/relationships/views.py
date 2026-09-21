"""API views for the relationships system (#3957)."""

from __future__ import annotations

from typing import Any

from django.db.models import Prefetch
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet, ReadOnlyModelViewSet

from world.mechanics.models import ModifierTarget
from world.relationships.constants import TieAudience
from world.relationships.filters import RelationshipCapstoneFilter
from world.relationships.models import (
    CharacterRelationship,
    RelationshipCapstone,
    RelationshipCondition,
    RelationshipLabel,
    RelationshipType,
)
from world.relationships.reads import (
    build_tie_page,
    entry_id_for,
    resolve_viewer_sheet,
    third_party_can_see,
    tie_audience,
    tie_stream,
)
from world.relationships.serializers import (
    AdvanceWriteSerializer,
    AllocationWriteSerializer,
    AwarenessWriteSerializer,
    DeclareWriteSerializer,
    LabelWriteSerializer,
    RelationshipCapstoneSerializer,
    RelationshipConditionSerializer,
    RelationshipTypeSerializer,
    ShiftWriteSerializer,
    SummaryWriteSerializer,
    TieSerializer,
    TieStreamItemSerializer,
    TieWriteResultSerializer,
)

NO_ACTIVE_CHARACTER_MESSAGE = "No active character."

# Sides prefetched for a batched read (#3957 review): labels ordered + select_related for
# label_payload's replaced_type_name gate and build_tie_page's mutuality check
# (declared_by_tenure.end_date), plus the relations build_tie_page/_row_to_payload read
# directly off each side.
_LABELS_PREFETCH = Prefetch(
    "labels",
    queryset=RelationshipLabel.objects.select_related(
        "type", "type__counterpart", "replaced__type", "declared_by_tenure"
    ).order_by("since"),
)


class RelationshipConditionViewSet(ReadOnlyModelViewSet):
    """List and retrieve relationship conditions."""

    queryset = RelationshipCondition.objects.prefetch_related(
        Prefetch(
            "gates_modifiers",
            queryset=ModifierTarget.objects.all(),
            to_attr="cached_gates_modifiers",
        ),
    )
    serializer_class = RelationshipConditionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None


class RelationshipTypeViewSet(ReadOnlyModelViewSet):
    """List and retrieve the catalogue of tie types (#3957)."""

    queryset = RelationshipType.objects.select_related("counterpart")
    serializer_class = RelationshipTypeSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["family", "valence"]


class RelationshipCapstoneViewSet(ReadOnlyModelViewSet):
    """Read-only ViewSet exposing the caller's RelationshipCapstone rows (#3957).

    Used by the frontend to populate the Soul Tether ritual perform form's
    capstone picker. The ``?other_character_sheet_id=`` filter narrows to
    capstones whose parent relationship involves a specific target character.
    """

    serializer_class = RelationshipCapstoneSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = PageNumberPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = RelationshipCapstoneFilter

    def get_queryset(self):  # type: ignore[override]
        """Return capstones authored on relationships the caller's sheets source.

        Numeric relationship state is author-private: scoped to rows whose parent
        side's ``source`` belongs to one of the caller's own characters, via a
        current (``end_date__isnull=True``) ``RosterTenure`` join (mirrors
        ``CharacterRelationshipViewSet.get_queryset``).
        """
        user = self.request.user
        return (
            RelationshipCapstone.objects.filter(
                relationship__source__roster_entry__tenures__player_data__account=user,
                relationship__source__roster_entry__tenures__end_date__isnull=True,
            )
            .select_related("journal_entry", "relationship")
            .distinct()
        )


class CharacterRelationshipViewSet(GenericViewSet):
    """One tie per audience: list is the caller's own sides; retrieve shapes by viewer (#3957).

    ``list`` and ``retrieve`` both emit ``TieSerializer`` rows built by
    ``reads.build_tie_page`` (batched even for ``retrieve``'s one-row page — same query cost,
    one shared implementation), but from different starting points: ``list`` scopes to the
    caller's own outbound sides (always audience OWNER — it's only ever the caller's own
    data), while ``retrieve`` accepts any pk and computes the viewer's actual audience,
    404ing for a third party with no public label, and for anyone but the owner/staff on a
    companion-target side (no second player to name on a public card). The seven POST
    actions converge on ``actions.definitions.relationships`` — the one seam telnet and the
    web share (``action.run()``).
    """

    permission_classes = [IsAuthenticated]
    serializer_class = TieSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["target", "target_companion"]

    # drf-spectacular sets this to True on the view instance while generating the
    # schema. Declaring the default here keeps get_queryset's guard a plain attribute
    # read rather than a getattr with a literal name (see the same guard on
    # ConsequenceOutcomeViewSet / GiftViewSet).
    swagger_fake_view = False

    def get_queryset(self):
        """Own sides only: a tenure join on ``source``, mirroring the capstone viewset.

        drf-spectacular introspects the filterset by calling ``get_queryset()`` with an
        anonymous dummy request; without this guard the user-filter would explode
        during schema generation. select_related/prefetch here is what makes ``list``'s
        page a fixed query count rather than one label/allocation/thread lookup per row.
        """
        if self.swagger_fake_view:
            return CharacterRelationship.objects.none()
        user = self.request.user
        return (
            CharacterRelationship.objects.filter(
                source__roster_entry__tenures__player_data__account=user,
                source__roster_entry__tenures__end_date__isnull=True,
            )
            .distinct()
            .select_related(
                "source",
                "source__character",
                "target",
                "target__character",
                "target__roster_entry",
                "target_companion",
                "allocation",
            )
            .prefetch_related(_LABELS_PREFETCH)
        )

    @extend_schema(responses=TieSerializer)
    def list(self, request):
        """The caller's own outbound sides, always shaped as their OWNER view."""
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        sides = list(page if page is not None else queryset)
        rows = build_tie_page(
            sides, viewer_sheet=None, is_staff=False, force_audience=TieAudience.OWNER
        )
        data = [self._row_to_payload(row) for row in rows]
        serializer = TieSerializer(data, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @extend_schema(responses=TieSerializer)
    def retrieve(self, request, pk=None):
        """One side of a tie, shaped for whoever is asking.

        Bypasses ``get_queryset()`` (own-sides-only) deliberately: any authenticated
        viewer may look up any side by pk, and ``tie_audience`` + ``third_party_can_see``
        decide what comes back — a third party with no open Public label gets a 404, not
        a 403, so a tie's mere existence is never leaked. A companion-target side 404s for
        anyone but the owner or staff, regardless of label visibility.
        """
        side = (
            CharacterRelationship.objects.select_related(
                "source",
                "source__character",
                "target",
                "target__character",
                "target_companion",
                "allocation",
            )
            .prefetch_related(_LABELS_PREFETCH)
            .filter(pk=pk)
            .first()
        )
        if side is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        viewer_sheet = resolve_viewer_sheet(request)
        is_staff = bool(request.user.is_staff)
        audience = tie_audience(side, viewer_sheet, is_staff)
        if audience == TieAudience.THIRD_PARTY and not third_party_can_see(side):
            return Response(status=status.HTTP_404_NOT_FOUND)
        if side.target_companion_id is not None and audience not in (
            TieAudience.OWNER,
            TieAudience.STAFF,
        ):
            return Response(status=status.HTTP_404_NOT_FOUND)
        row = build_tie_page(
            [side], viewer_sheet=viewer_sheet, is_staff=is_staff, force_audience=audience
        )[0]
        return Response(TieSerializer(self._row_to_payload(row)).data)

    @extend_schema(responses=TieStreamItemSerializer(many=True))
    @action(detail=True, methods=["get"], pagination_class=None)
    def stream(self, request, pk=None):
        """Journal entries and shared scenes between the two sides, viewer-filtered."""
        side = (
            CharacterRelationship.objects.select_related("source", "target").filter(pk=pk).first()
        )
        if side is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        viewer_sheet = resolve_viewer_sheet(request)
        is_staff = bool(request.user.is_staff)
        audience = tie_audience(side, viewer_sheet, is_staff)
        if audience == TieAudience.THIRD_PARTY and not third_party_can_see(side):
            return Response(status=status.HTTP_404_NOT_FOUND)
        if side.target_companion_id is not None and audience not in (
            TieAudience.OWNER,
            TieAudience.STAFF,
        ):
            return Response(status=status.HTTP_404_NOT_FOUND)
        items = tie_stream(side, viewer_sheet, is_staff)
        return Response(TieStreamItemSerializer(items, many=True).data)

    # -- shared read-side plumbing ------------------------------------------------

    def _row_to_payload(self, row: dict[str, Any]) -> dict[str, Any]:
        """A ``build_tie_page`` row plus the side's own scalars, in ``TieSerializer``'s shape."""
        side = row["side"]
        return {
            "id": side.pk,
            "source": side.source_id,
            "target": side.target_id,
            "target_companion": side.target_companion_id,
            "target_name": side.target_name,
            "other_sheet_id": side.target_id,
            "other_entry_id": entry_id_for(side.target),
            "audience": row["audience"],
            "labels": row["labels"],
            "depth": row["depth"],
            "next_tier_threshold": row["next_tier_threshold"],
            "breakdown": row["breakdown"],
            "summary": side.summary,
            "ap_this_week": row["ap_this_week"],
            "thread": row["thread"],
            "is_soul_tether": side.is_soul_tether,
        }

    # -- write plumbing -------------------------------------------------------------

    def _resolve_actor(self, request):
        """Return the caller's selected character if they own its sheet."""
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.roster.services.selection import character_for_request  # noqa: PLC0415

        actor = character_for_request(request, entry_id=None)
        if actor is None:
            return None, NO_ACTIVE_CHARACTER_MESSAGE
        try:
            sheet = actor.sheet_data
        except ObjectDoesNotExist:
            return None, NO_ACTIVE_CHARACTER_MESSAGE
        if sheet.character.db_account_id != request.user.pk:
            return None, NO_ACTIVE_CHARACTER_MESSAGE
        return actor, ""

    def _resolve_target_sheet(self, target_persona_id: int):
        """Resolve a target persona ID to its CharacterSheet."""
        from world.scenes.models import Persona  # noqa: PLC0415

        return (
            Persona.objects.filter(pk=target_persona_id).select_related("character_sheet").first()
        )

    def _resolve_target_companion(self, target_companion_id: int):
        """Resolve a bonded, unreleased Companion by pk, or None (#3575)."""
        from world.companions.models import Companion  # noqa: PLC0415

        return (
            Companion.objects.filter(pk=target_companion_id, released_at__isnull=True)
            .select_related("owner")
            .first()
        )

    def _resolve_target(self, data: dict) -> tuple[Any, Any, Response | None]:
        """``(target_sheet, target_companion, None)`` or ``(None, None, error_response)``."""
        if data.get("target_persona_id") is not None:
            persona = self._resolve_target_sheet(data["target_persona_id"])
            if persona is None:
                return None, None, self._error_response("Target persona not found.")
            return persona.character_sheet, None, None
        companion = self._resolve_target_companion(data["target_companion_id"])
        if companion is None:
            return None, None, self._error_response("Target companion not found.")
        return None, companion, None

    def _resolve_label(self, label_id: int):
        return (
            RelationshipLabel.objects.select_related("relationship", "type")
            .filter(pk=label_id)
            .first()
        )

    def _error_response(self, message: str) -> Response:
        return Response(
            {"success": False, "message": message, "data": {}},
            status=status.HTTP_400_BAD_REQUEST,
        )

    def _result_response(self, result) -> Response:
        if not result.success:
            return self._error_response(result.message)
        return Response(
            {"success": True, "message": result.message, "data": result.data or {}},
            status=status.HTTP_200_OK,
        )

    def _validation_error_response(self, serializer) -> Response:
        """Wrap DRF's field-dict validation errors into the same honest write shape (#3957
        review) — a caller reads one ``message``, not a per-field error tree.
        """
        first_field_errors = next(iter(serializer.errors.values()))
        return self._error_response(str(first_field_errors[0]))

    @extend_schema(request=DeclareWriteSerializer, responses=TieWriteResultSerializer)
    @action(detail=False, methods=["post"])
    def declare(self, request):
        """Name a type on the caller's side of a tie (#3957)."""
        from actions.definitions.relationships import DeclareLabelAction  # noqa: PLC0415

        actor, error = self._resolve_actor(request)
        if actor is None:
            return self._error_response(error)
        serializer = DeclareWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return self._validation_error_response(serializer)
        data = serializer.validated_data
        target_sheet, target_companion, err = self._resolve_target(data)
        if err is not None:
            return err
        rel_type = RelationshipType.objects.filter(pk=data["type_id"]).first()
        if rel_type is None:
            return self._error_response("Unknown type.")
        result = DeclareLabelAction().run(
            actor=actor,
            target_sheet=target_sheet,
            target_companion=target_companion,
            type=rel_type,
            awareness=data["awareness"],
        )
        return self._result_response(result)

    @extend_schema(request=ShiftWriteSerializer, responses=TieWriteResultSerializer)
    @action(detail=False, methods=["post"])
    def shift(self, request):
        """Change one label into another (#3957)."""
        from actions.definitions.relationships import ShiftLabelAction  # noqa: PLC0415

        actor, error = self._resolve_actor(request)
        if actor is None:
            return self._error_response(error)
        serializer = ShiftWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return self._validation_error_response(serializer)
        data = serializer.validated_data
        label = self._resolve_label(data["label_id"])
        if label is None:
            return self._error_response("Label not found.")
        new_type = RelationshipType.objects.filter(pk=data["new_type_id"]).first()
        if new_type is None:
            return self._error_response("Unknown type.")
        result = ShiftLabelAction().run(
            actor=actor, label=label, new_type=new_type, note=data.get("note", "")
        )
        return self._result_response(result)

    @extend_schema(request=LabelWriteSerializer, responses=TieWriteResultSerializer)
    @action(detail=False, methods=["post"])
    def end(self, request):
        """End an open label; it shows as former from then on (#3957)."""
        from actions.definitions.relationships import EndLabelAction  # noqa: PLC0415

        actor, error = self._resolve_actor(request)
        if actor is None:
            return self._error_response(error)
        serializer = LabelWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return self._validation_error_response(serializer)
        data = serializer.validated_data
        label = self._resolve_label(data["label_id"])
        if label is None:
            return self._error_response("Label not found.")
        result = EndLabelAction().run(actor=actor, label=label)
        return self._result_response(result)

    @extend_schema(request=AwarenessWriteSerializer, responses=TieWriteResultSerializer)
    @action(detail=False, methods=["post"])
    def awareness(self, request):
        """Move a label's awareness forward (#3957)."""
        from actions.definitions.relationships import AdvanceLabelAwarenessAction  # noqa: PLC0415

        actor, error = self._resolve_actor(request)
        if actor is None:
            return self._error_response(error)
        serializer = AwarenessWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return self._validation_error_response(serializer)
        data = serializer.validated_data
        label = self._resolve_label(data["label_id"])
        if label is None:
            return self._error_response("Label not found.")
        result = AdvanceLabelAwarenessAction().run(
            actor=actor, label=label, awareness=data["awareness"]
        )
        return self._result_response(result)

    @extend_schema(request=AllocationWriteSerializer, responses=TieWriteResultSerializer)
    @action(detail=False, methods=["post"])
    def allocation(self, request):
        """Set this week's AP toward one side of a tie (#3957)."""
        from actions.definitions.relationships import SetTieAllocationAction  # noqa: PLC0415

        actor, error = self._resolve_actor(request)
        if actor is None:
            return self._error_response(error)
        serializer = AllocationWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return self._validation_error_response(serializer)
        data = serializer.validated_data
        target_sheet, target_companion, err = self._resolve_target(data)
        if err is not None:
            return err
        result = SetTieAllocationAction().run(
            actor=actor,
            target_sheet=target_sheet,
            target_companion=target_companion,
            ap_amount=data["ap_amount"],
        )
        return self._result_response(result)

    @extend_schema(request=AdvanceWriteSerializer, responses=TieWriteResultSerializer)
    @action(detail=False, methods=["post"])
    def advance(self, request):
        """Claim the next tier with a capstone journal entry and XP (#3957)."""
        from actions.definitions.relationships import AdvanceRelationshipTierAction  # noqa: PLC0415
        from world.journals.models import JournalEntry  # noqa: PLC0415

        actor, error = self._resolve_actor(request)
        if actor is None:
            return self._error_response(error)
        serializer = AdvanceWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return self._validation_error_response(serializer)
        data = serializer.validated_data
        target_sheet, _target_companion, err = self._resolve_target(data)
        if err is not None:
            return err
        entry = JournalEntry.objects.filter(pk=data["journal_entry_id"]).first()
        if entry is None:
            return self._error_response("Entry not found.")
        result = AdvanceRelationshipTierAction().run(
            actor=actor, target_sheet=target_sheet, journal_entry=entry
        )
        return self._result_response(result)

    @extend_schema(request=SummaryWriteSerializer, responses=TieWriteResultSerializer)
    @action(detail=False, methods=["post"])
    def summary(self, request):
        """Set the player's own paragraph on one side of a tie (#3957)."""
        from actions.definitions.relationships import SetTieSummaryAction  # noqa: PLC0415

        actor, error = self._resolve_actor(request)
        if actor is None:
            return self._error_response(error)
        serializer = SummaryWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return self._validation_error_response(serializer)
        data = serializer.validated_data
        target_sheet, target_companion, err = self._resolve_target(data)
        if err is not None:
            return err
        result = SetTieSummaryAction().run(
            actor=actor,
            target_sheet=target_sheet,
            target_companion=target_companion,
            summary=data["summary"],
        )
        return self._result_response(result)
