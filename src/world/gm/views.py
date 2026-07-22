"""ViewSets for the GM system."""

from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Count, Q, QuerySet
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import generics, mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from world.distinctions.models import CharacterDistinction, Distinction
from world.gm.constants import GMApplicationStatus, GMTableStatus, TableRequestKind
from world.gm.filters import (
    CatalogSuggestionFilter,
    GMApplicationFilter,
    GMProfileFilter,
    GMTableFilter,
    GMTableMembershipFilter,
    TableUpdateRequestFilter,
)
from world.gm.models import (
    CatalogSuggestion,
    GMApplication,
    GMProfile,
    GMRosterInvite,
    GMTable,
    GMTableMembership,
    TableUpdateRequest,
)
from world.gm.permissions import IsGM, IsGMOrStaff
from world.gm.serializers import (
    CatalogSuggestionDetailSerializer,
    DemandRansomSerializer,
    GMApplicationActionSerializer,
    GMApplicationCreateSerializer,
    GMApplicationDetailSerializer,
    GMApplicationQueueSerializer,
    GMEvidenceSummarySerializer,
    GMInviteClaimSerializer,
    GMInviteRevokeSerializer,
    GMProfileSerializer,
    GMRosterInviteSerializer,
    GMTableMembershipSerializer,
    GMTableSerializer,
    PromoteGMInputSerializer,
    TableUpdateRequestCreateSerializer,
    TableUpdateRequestSerializer,
    TableUpdateRequestSignoffSerializer,
)
from world.gm.services import (
    TableRequestError,
    archive_table,
    gm_application_queue,
    gm_evidence_summary,
    join_table,
    leave_table,
    promote_gm,
    set_looking_for_table,
    signoff_table_update_request,
    submit_distinction_change_request,
    submit_profile_text_request,
    transfer_ownership as transfer_ownership_service,
    withdraw_table_update_request,
)
from world.player_submissions.constants import SubmissionStatus
from world.roster.models.applications import RosterApplication
from world.stories.pagination import StandardResultsSetPagination


class GMApplicationViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """GM application management.

    Create: any authenticated player.
    List/Retrieve/Update: staff only.
    """

    queryset = GMApplication.objects.select_related("account", "reviewed_by").order_by(
        "-created_at"
    )
    filterset_class = GMApplicationFilter
    filter_backends = [DjangoFilterBackend]
    pagination_class = StandardResultsSetPagination

    def get_serializer_class(self) -> type[serializers.Serializer]:
        if self.action == "create":
            return GMApplicationCreateSerializer
        return GMApplicationDetailSerializer

    def get_permissions(self) -> list:
        if self.action == "create":
            return [IsAuthenticated()]
        return [IsAdminUser()]

    def perform_update(self, serializer: serializers.Serializer) -> None:
        # Fetch the pre-update status from the DB to avoid relying on
        # DRF's internal timing of when instance mutation happens.
        previous_status = GMApplication.objects.values_list("status", flat=True).get(
            pk=serializer.instance.pk
        )
        instance = serializer.save(reviewed_by=self.request.user)
        if (
            instance.status == GMApplicationStatus.APPROVED
            and previous_status != GMApplicationStatus.APPROVED
        ):
            GMProfile.objects.get_or_create(
                account=instance.account,
                defaults={
                    "approved_at": timezone.now(),
                    "approved_by": self.request.user,
                },
            )


class CatalogSuggestionViewSet(
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Staff triage of GM scenario-catalog suggestions (#2127).

    No create action — a suggestion is only ever created through
    ``SubmitCatalogSuggestionAction`` (the generic REGISTRY dispatch seam both
    telnet's ``gm suggest`` and web already use), mirroring
    ``SystemErrorReportViewSet``'s system-authored shape. List/retrieve/update
    are staff-only.
    """

    queryset = CatalogSuggestion.objects.select_related(
        "submitted_by", "situation_kind", "reviewer"
    ).order_by("-created_at")
    filterset_class = CatalogSuggestionFilter
    filter_backends = [DjangoFilterBackend]
    pagination_class = StandardResultsSetPagination
    serializer_class = CatalogSuggestionDetailSerializer
    permission_classes = [IsAdminUser]

    def perform_update(self, serializer: serializers.Serializer) -> None:
        previous_status = CatalogSuggestion.objects.values_list("status", flat=True).get(
            pk=serializer.instance.pk
        )
        instance = serializer.save(reviewer=self.request.user)
        if instance.status != SubmissionStatus.OPEN and previous_status == SubmissionStatus.OPEN:
            instance.resolved_at = timezone.now()
            instance.save(update_fields=["resolved_at"])


class GMProfileViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Read-only list of approved GM profiles.

    Accessible by any authenticated user so players can pick a GM when
    offering their story. Supports ``?search=<username>`` for autocomplete.
    """

    queryset = GMProfile.objects.select_related("account").order_by("account__username")
    serializer_class = GMProfileSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = GMProfileFilter
    pagination_class = StandardResultsSetPagination

    @extend_schema(request=PromoteGMInputSerializer, responses=GMProfileSerializer)
    @action(detail=True, methods=["post"], permission_classes=[IsAdminUser])
    def promote(self, request: Request, pk: str | None = None) -> Response:
        """Staff changes a GM's trust level (promotion or demotion), with an audit row.

        Same-level and unknown-level input is rejected in
        ``PromoteGMInputSerializer.validate`` so ``promote_gm``'s ``ValueError``
        guard never fires from user input.
        """
        profile = self.get_object()
        serializer = PromoteGMInputSerializer(data=request.data, context={"profile": profile})
        serializer.is_valid(raise_exception=True)
        promote_gm(
            profile,
            serializer.validated_data["new_level"],
            changed_by=request.user,
            reason=serializer.validated_data["reason"],
        )
        return Response(GMProfileSerializer(profile).data)

    @extend_schema(responses=GMEvidenceSummarySerializer)
    @action(detail=True, methods=["get"], permission_classes=[IsAdminUser])
    def evidence(self, request: Request, pk: str | None = None) -> Response:
        """Staff-only aggregate track record backing a level-change decision."""
        profile = self.get_object()
        summary = gm_evidence_summary(profile)
        return Response(GMEvidenceSummarySerializer(summary).data)


class GMTableViewSet(viewsets.ModelViewSet):
    """GM table management.

    Staff sees all tables. GMs see their own tables. Players see tables where any
    of their personas has an active GMTableMembership (left_at__isnull=True).

    Persona-to-account chain: GMTableMembership.persona → Persona.character_sheet
    → CharacterSheet.character (ObjectDB) → ObjectDB.db_account.

    Archive and transfer ownership are staff-only lifecycle actions.
    """

    queryset = GMTable.objects.select_related("gm__account").order_by("-created_at")
    serializer_class = GMTableSerializer
    filterset_class = GMTableFilter
    filter_backends = [DjangoFilterBackend]
    pagination_class = StandardResultsSetPagination
    permission_classes = [IsAuthenticated]

    def _annotate_counts(self, qs: QuerySet[GMTable]) -> QuerySet[GMTable]:
        """Annotate ``member_count`` and ``story_count`` once per queryset.

        Replaces per-row ``.count()`` calls in
        ``GMTableSerializer.get_member_count`` / ``get_story_count`` with a
        single grouped query.
        """
        return qs.annotate(
            member_count=Count(
                "memberships",
                filter=Q(memberships__left_at__isnull=True),
                distinct=True,
            ),
            story_count=Count("primary_stories", distinct=True),
        )

    def get_queryset(self) -> QuerySet[GMTable]:
        qs = super().get_queryset()
        user = self.request.user
        if user.is_staff:
            return self._annotate_counts(qs)
        # GM owner of the table OR has an active membership via any persona.
        return self._annotate_counts(
            qs.filter(
                Q(gm__account=user)
                | Q(
                    memberships__persona__character_sheet__character__db_account=user,
                    memberships__left_at__isnull=True,
                )
            ).distinct()
        )

    def _get_viewer_member_table_ids(self) -> set[int]:
        """Return GMTable ids where the requesting user has an active membership.

        One query per request — used by ``GMTableSerializer.get_viewer_role``
        to avoid per-row ``.exists()`` calls.
        """
        user = self.request.user
        if not user.is_authenticated:
            return set()
        return set(
            GMTableMembership.objects.filter(
                persona__character_sheet__character__db_account=user,
                left_at__isnull=True,
            )
            .values_list("table_id", flat=True)
            .distinct()
        )

    def _get_viewer_story_participant_table_ids(self) -> set[int]:
        """Return GMTable ids where the requesting user participates in a story.

        Used to derive the ``guest`` viewer-role without a per-row query.
        """
        from world.stories.models import StoryParticipation  # noqa: PLC0415

        user = self.request.user
        if not user.is_authenticated:
            return set()
        return set(
            StoryParticipation.objects.filter(
                story__primary_table__isnull=False,
                character__db_account=user,
                is_active=True,
            )
            .values_list("story__primary_table_id", flat=True)
            .distinct()
        )

    def get_serializer_context(self) -> dict:
        context = super().get_serializer_context()
        context["viewer_member_table_ids"] = self._get_viewer_member_table_ids()
        context["viewer_story_participant_table_ids"] = (
            self._get_viewer_story_participant_table_ids()
        )
        return context

    @action(detail=True, methods=["post"], permission_classes=[IsAdminUser])
    def archive(self, request: Request, pk: str | None = None) -> Response:
        table = self.get_object()
        archive_table(table)
        return Response(GMTableSerializer(table, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"], permission_classes=[IsAdminUser])
    def transfer_ownership(self, request: Request, pk: str | None = None) -> Response:
        new_gm_id = request.data.get("new_gm")
        if not new_gm_id:
            return Response(
                {"new_gm": "This field is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        table = self.get_object()
        new_gm = get_object_or_404(GMProfile, pk=new_gm_id)
        transfer_ownership_service(table, new_gm)
        return Response(GMTableSerializer(table, context=self.get_serializer_context()).data)


class GMTableMembershipViewSet(viewsets.ModelViewSet):
    """GM table membership management.

    Staff sees all memberships. GMs (table owners) see all memberships at their
    tables. Authenticated players see all memberships at tables where any of
    their personas has an active membership — this gives them the member roster
    for tables they belong to.

    Persona-to-account chain: GMTableMembership.persona → Persona.character_sheet
    → CharacterSheet.character (ObjectDB) → ObjectDB.db_account.

    Creation uses the join_table service to apply temporary-persona validation.
    Destroy is a soft-leave — the record remains with left_at set.
    """

    queryset = GMTableMembership.objects.select_related("table", "persona").order_by("-pk")
    serializer_class = GMTableMembershipSerializer
    filterset_class = GMTableMembershipFilter
    filter_backends = [DjangoFilterBackend]
    pagination_class = StandardResultsSetPagination
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[GMTableMembership]:
        qs = super().get_queryset()
        user = self.request.user
        if user.is_staff:
            return qs
        # GM owns the table OR the user has an active membership at the table.
        # The second branch gives members access to the full membership roster
        # for any table they actively belong to (needed for Wave 4 Members tab).
        return qs.filter(
            Q(table__gm__account=user)
            | Q(
                table__memberships__persona__character_sheet__character__db_account=user,
                table__memberships__left_at__isnull=True,
            )
        ).distinct()

    def perform_create(self, serializer: serializers.Serializer) -> None:
        """Create membership via service to enforce TEMPORARY rejection.

        Idempotent: if an active membership already exists, ``join_table``
        returns it rather than creating a duplicate. The HTTP response
        will still be 201 in either case — DRF's CreateModelMixin does
        not distinguish create-vs-already-exists, and semantic correctness
        here is minor compared to keeping a single code path.
        """
        table = serializer.validated_data["table"]
        persona = serializer.validated_data["persona"]
        try:
            membership = join_table(table, persona)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        serializer.instance = membership

    def perform_destroy(self, instance: GMTableMembership) -> None:
        leave_table(instance)


class GMRosterInviteViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """GM invites for specific roster characters.

    - create: GM only, must oversee the character (validated in serializer)
    - list/retrieve: scoped to GM's invites (staff sees all)
    - destroy: revokes unclaimed invites (validated in serializer)
    """

    serializer_class = GMRosterInviteSerializer
    pagination_class = StandardResultsSetPagination
    permission_classes = [IsGMOrStaff]

    def get_queryset(self) -> QuerySet[GMRosterInvite]:
        qs = GMRosterInvite.objects.select_related(
            "roster_entry", "created_by__account", "claimed_by"
        ).order_by("-created_at")
        user = self.request.user
        if user.is_staff:
            return qs
        return qs.filter(created_by__account=user)

    def destroy(self, request: Request, *args: object, **kwargs: object) -> Response:
        instance = self.get_object()
        serializer = GMInviteRevokeSerializer(
            instance,
            data={},
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class GMApplicationQueueView(generics.ListAPIView):
    """Read-only list of pending applications for this GM's characters."""

    serializer_class = GMApplicationQueueSerializer
    pagination_class = StandardResultsSetPagination
    permission_classes = [IsGMOrStaff]

    def get_queryset(self) -> QuerySet[RosterApplication]:
        from world.roster.models.choices import ApplicationStatus  # noqa: PLC0415

        user = self.request.user
        if user.is_staff:
            # Staff see all pending apps across all GM tables.
            return (
                RosterApplication.objects.filter(
                    status=ApplicationStatus.PENDING,
                    character__story_participations__is_active=True,
                    character__story_participations__story__primary_table__isnull=False,
                    character__story_participations__story__primary_table__status=(
                        GMTableStatus.ACTIVE
                    ),
                )
                .select_related("character", "player_data__account")
                .distinct()
            )
        return gm_application_queue(user.gm_profile)


class GMApplicationActionView(APIView):
    """GM approves or denies a pending application in their queue.

    URL path: /api/gm/queue/<id>/<action>/ where action is 'approve' or 'deny'.
    """

    permission_classes = [IsGM]

    @transaction.atomic
    def post(self, request: Request, pk: int, action: str) -> Response:
        application = get_object_or_404(RosterApplication, pk=pk)
        serializer = GMApplicationActionSerializer(
            data={
                "action": action,
                "review_notes": request.data.get("review_notes", ""),
            },
            context={"request": request, "application": application},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"status": "ok"})


class GMInviteClaimView(APIView):
    """Logged-in user claims an invite by code."""

    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request: Request) -> Response:
        serializer = GMInviteClaimSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        application = serializer.save()
        return Response(
            {"application_id": application.pk},
            status=status.HTTP_201_CREATED,
        )


class DemandRansomView(APIView):
    """Staff/GM raises a crowdfundable ransom for a held captive (#1500).

    POST ``/api/gm/demand-ransom/`` with ``{captivity_id, amount?}``. Creates a
    RANSOM project standing in the captive's cell that anyone may donate toward;
    the captive is freed the instant it is fully funded. The same
    ``demand_ransom_project`` service backs the telnet ``demandransom`` command.
    """

    permission_classes = [IsGMOrStaff]

    @transaction.atomic
    def post(self, request: Request) -> Response:
        serializer = DemandRansomSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        project = serializer.save()
        return Response(
            {"project_id": project.pk, "threshold_target": project.threshold_target},
            status=status.HTTP_201_CREATED,
        )


class GMDashboardView(APIView):
    """GET /api/gm/dashboard/ — the GM's story-shaped dashboard (#2004).

    Composes the existing gm-queue (episodes ready, pending AGM claims,
    assigned sessions, waiting-for-GM) with the GM's tables, pending story
    offers, and evidence summary. Role-gated via IsGM.
    """

    permission_classes = [IsGM]

    def get(self, request: Request) -> Response:
        """Return the GM's dashboard aggregation."""
        from world.gm.services import gm_evidence_summary  # noqa: PLC0415
        from world.stories.constants import (  # noqa: PLC0415
            StoryGMOfferStatus,
        )
        from world.stories.models import (  # noqa: PLC0415
            StoryGMOffer,
        )
        from world.stories.views import _collect_gm_queue  # noqa: PLC0415

        gm_profile = request.user.gm_profile

        # Reuse the existing gm-queue aggregation.
        buckets = _collect_gm_queue(gm_profile)

        # My tables with basic counts.
        my_tables = list(
            GMTable.objects.filter(gm=gm_profile, status=GMTableStatus.ACTIVE)
            .annotate(
                membership_count=Count("memberships", filter=Q(memberships__left_at__isnull=True)),
            )
            .values("id", "name", "membership_count")
        )

        # Pending story offers addressed to this GM.
        pending_offers = list(
            StoryGMOffer.objects.filter(
                offered_to=gm_profile, status=StoryGMOfferStatus.PENDING
            ).values("id", "story__title", "created_at")
        )

        # Evidence summary (self-view of what staff sees).
        evidence = gm_evidence_summary(gm_profile)

        return Response(
            {
                "episodes_ready_to_run": buckets.episodes_ready,
                "pending_agm_claims": buckets.pending_claims,
                "assigned_session_requests": buckets.assigned_requests,
                "waiting_for_gm": buckets.waiting_for_gm,
                "open_group_requests": buckets.open_group_requests,
                "my_tables": my_tables,
                "pending_story_offers": pending_offers,
                "evidence_summary": {
                    "level": evidence.level,
                    "stories_running": evidence.stories_running,
                    "beats_completed_by_risk": evidence.beats_completed_by_risk,
                    "last_active_at": evidence.last_active_at,
                },
            }
        )


# --- Looking-for-table (#2431) -----------------------------------------------


class LookingForTableToggleView(APIView):
    """Player toggles their own looking-for-table flag.

    POST /api/roster/looking-for-table/ with body {"looking": true/false}.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        """Set or clear the looking-for-table flag on the requesting user's PlayerData."""
        looking = request.data.get("looking")
        if looking is None:
            return Response(
                {"detail": "looking field is required (true or false)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not isinstance(looking, bool):
            return Response(
                {"detail": "looking must be a boolean."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            player_data = request.user.player_data
        except AttributeError:
            return Response(
                {"detail": "Player data not found."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        set_looking_for_table(player_data, looking=looking)
        return Response(
            {"looking_for_table": player_data.looking_for_table},
            status=status.HTTP_200_OK,
        )


class LookingForTableEntrySerializer(serializers.Serializer):
    """One entry in the GM's looking-for-table browse list."""

    character_name = serializers.SerializerMethodField()
    player_display = serializers.SerializerMethodField()
    path_name = serializers.SerializerMethodField()
    character_level = serializers.SerializerMethodField()
    glimpse_story = serializers.SerializerMethodField()
    flagged_at = serializers.SerializerMethodField()

    def get_character_name(self, obj) -> str:
        try:
            return obj.character_sheet.character.name
        except AttributeError:
            return ""

    def get_player_display(self, obj) -> str:
        tenure = obj.current_tenure
        if tenure and tenure.player_data:
            return tenure.player_data.display_name
        return ""

    def get_path_name(self, obj) -> str:
        try:
            levels = obj.character_sheet.cached_character_class_levels
            if levels:
                path = levels[0].character_class.path
                return path.name if path else ""
        except Exception:  # noqa: BLE001, S110
            pass
        return ""

    def get_character_level(self, obj) -> int:
        try:
            levels = obj.character_sheet.cached_character_class_levels
            if levels:
                return max(ccl.level for ccl in levels)
        except Exception:  # noqa: BLE001, S110
            pass
        return 0

    def get_glimpse_story(self, obj) -> str:
        try:
            aura = obj.character_sheet.character.aura
            return aura.glimpse_story or ""
        except Exception:  # noqa: BLE001
            return ""

    def get_flagged_at(self, obj):
        tenure = obj.current_tenure
        if tenure and tenure.player_data:
            return tenure.player_data.looking_for_table_set_at
        return None


class LookingForTableBrowseView(APIView):
    """GM browses players looking for tables.

    GET /api/gm/looking-for-table/ — returns a list of characters whose
    PlayerData.looking_for_table is True, with rich context (path, level,
    glimpse story) for tailoring invitations.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        """Return looking-for-table players, sorted by most recently flagged."""
        # Only GMs (accounts with a GMProfile) can browse
        if not hasattr(request.user, "gm_profile"):
            return Response(
                {"detail": "Only GMs can browse the looking-for-table list."},
                status=status.HTTP_403_FORBIDDEN,
            )

        from world.roster.models import RosterEntry  # noqa: PLC0415

        entries = (
            RosterEntry.objects.filter(
                tenures__end_date__isnull=True,
                tenures__player_data__looking_for_table=True,
            )
            .select_related("character_sheet__character")
            .prefetch_related("tenures__player_data")  # noqa: PREFETCH_STRING
            .distinct()
            .order_by("-tenures__player_data__looking_for_table_set_at")
        )
        serializer = LookingForTableEntrySerializer(entries, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class TableUpdateRequestViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Player-submitted sheet-update requests (#2631).

    Players see their own requests; table GMs additionally see requests on
    their tables; staff sees all. Creation validates the membership belongs to
    the caller. ``signoff`` (GM) and ``withdraw`` (player) drive the state
    machine through the service layer.
    """

    queryset = TableUpdateRequest.objects.select_related(
        "membership__table__gm__account",
        "membership__persona__character_sheet",
        "resolved_by",
    ).order_by("-created_at")
    serializer_class = TableUpdateRequestSerializer
    filterset_class = TableUpdateRequestFilter
    filter_backends = [DjangoFilterBackend]
    pagination_class = StandardResultsSetPagination
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[TableUpdateRequest]:
        qs = super().get_queryset()
        user = self.request.user
        if user.is_staff:
            return qs
        return qs.filter(
            Q(membership__persona__character_sheet__character__db_account=user)
            | Q(membership__table__gm__account=user)
        ).distinct()

    @extend_schema(
        request=TableUpdateRequestCreateSerializer,
        responses={201: TableUpdateRequestSerializer},
    )
    def create(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Submit a request on one of the caller's own active memberships."""
        input_serializer = TableUpdateRequestCreateSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        data = input_serializer.validated_data

        membership = data["membership"]
        owner = membership.persona.character_sheet.character.db_account
        if owner != request.user:
            msg = "That table membership is not yours."
            raise serializers.ValidationError(msg)

        try:
            if data["kind"] == TableRequestKind.PROFILE_TEXT:
                update_request = submit_profile_text_request(
                    membership,
                    field=data["field"],
                    proposed_text=data["proposed_text"],
                    reasoning=data["reasoning"],
                )
            else:
                distinction = (
                    Distinction.objects.filter(pk=data["distinction"]).first()
                    if data.get("distinction")
                    else None
                )
                character_distinction = (
                    CharacterDistinction.objects.filter(pk=data["character_distinction"]).first()
                    if data.get("character_distinction")
                    else None
                )
                update_request = submit_distinction_change_request(
                    membership,
                    action=data["action"],
                    distinction=distinction,
                    character_distinction=character_distinction,
                    rank=data.get("rank", 1),
                    reasoning=data["reasoning"],
                )
        except TableRequestError as exc:
            raise serializers.ValidationError(exc.user_message) from exc
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc

        output = TableUpdateRequestSerializer(update_request)
        return Response(output.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=TableUpdateRequestSignoffSerializer,
        responses={200: TableUpdateRequestSerializer},
    )
    @action(detail=True, methods=["post"])
    def signoff(self, request: Request, pk: str | None = None) -> Response:
        """Approve or reject a pending request (table GM or staff)."""
        update_request = self.get_object()
        input_serializer = TableUpdateRequestSignoffSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        gm_profile = GMProfile.objects.filter(account=request.user).first()
        if gm_profile is None:
            msg = "You are not a GM."
            raise serializers.ValidationError(msg)

        try:
            update_request = signoff_table_update_request(
                update_request,
                gm_profile,
                approve=input_serializer.validated_data["approve"],
                notes=input_serializer.validated_data.get("notes", ""),
            )
        except TableRequestError as exc:
            raise serializers.ValidationError(exc.user_message) from exc

        return Response(TableUpdateRequestSerializer(update_request).data)

    @extend_schema(request=None, responses={200: TableUpdateRequestSerializer})
    @action(detail=True, methods=["post"])
    def withdraw(self, request: Request, pk: str | None = None) -> Response:
        """Withdraw the caller's own pending request."""
        update_request = self.get_object()
        owner = update_request.membership.persona.character_sheet.character.db_account
        if owner != request.user and not request.user.is_staff:
            msg = "You may only withdraw your own requests."
            raise serializers.ValidationError(msg)

        try:
            withdraw_table_update_request(update_request)
        except TableRequestError as exc:
            raise serializers.ValidationError(exc.user_message) from exc

        return Response(TableUpdateRequestSerializer(update_request).data)
