from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from http import HTTPMethod
from typing import TYPE_CHECKING, Any, cast

from django.db import models, transaction
from django.db.models import Count, Manager, Prefetch, QuerySet
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from evennia.accounts.models import AccountDB
from rest_framework import filters, mixins, permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer
from rest_framework.views import APIView

from evennia_extensions.models import PlayerData
from world.character_sheets.models import CharacterSheet
from world.narrative.permissions import IsStoryLeadGMOrStaff
from world.stories.constants import (
    AssistantClaimStatus,
    BeatVisibility,
    SessionRequestStatus,
    StoryScope,
)
from world.stories.exceptions import (
    CustodyClearanceAuthorityError,
    CustodyClearanceStateError,
    EraAdvanceError,
    StoryGMOfferError,
)
from world.stories.filters import (
    AggregateBeatContributionFilter,
    AssistantGMClaimFilter,
    BeatFilter,
    ChapterFilter,
    CustodyClearanceFilter,
    EpisodeFilter,
    EpisodeProgressionRequirementFilter,
    EpisodeSceneFilter,
    EraFilter,
    GlobalStoryProgressFilter,
    GroupStoryProgressFilter,
    PlayerTrustFilter,
    SessionRequestFilter,
    StakeContractActivationFilter,
    StakeFilter,
    StakeResolutionFilter,
    StakeRewardLineFilter,
    StakeTemplateFilter,
    StoryFeedbackFilter,
    StoryFilter,
    StoryGMOfferFilter,
    StoryNoteFilter,
    StoryParticipationFilter,
    StoryProtectedSubjectFilter,
    TableBulletinPostFilter,
    TableBulletinReplyFilter,
    TransitionFilter,
    TransitionRequiredOutcomeFilter,
)
from world.stories.models import (
    AggregateBeatContribution,
    AssistantGMClaim,
    Beat,
    Chapter,
    CrossoverInvite,
    CustodyClearance,
    Episode,
    EpisodeProgressionRequirement,
    EpisodeScene,
    Era,
    GlobalStoryProgress,
    GroupStoryProgress,
    PlayerTrust,
    RiskCalibration,
    SessionRequest,
    Stake,
    StakeContractActivation,
    StakeResolution,
    StakeRewardLine,
    StakeTemplate,
    Story,
    StoryFeedback,
    StoryGMOffer,
    StoryNote,
    StoryParticipation,
    StoryProgress,
    StoryProtectedSubject,
    TableBulletinPost,
    TableBulletinReply,
    Transition,
    TransitionRequiredOutcome,
    TreasuredSignoff,
)
from world.stories.pagination import (
    LargeResultsSetPagination,
    SmallResultsSetPagination,
    StandardResultsSetPagination,
)
from world.stories.permissions import (
    VIEWER_ROLE_NO_ACCESS,
    CanAccessStoryNotes,
    CanAuthorBulletinPost,
    CanDetachStoryFromTable,
    CanMarkBeat,
    CanParticipateInStory,
    CanReplyToBulletinPost,
    CanResolveStake,
    CanViewBeatStakesSummary,
    IsAccountOfCharacterSheet,
    IsBeatStoryOwnerOrStaff,
    IsBeatStoryOwnerOrStaffForAvailability,
    IsBulletinReplyAuthorOrStaff,
    IsChapterStoryOwnerOrStaff,
    IsClaimantOrLeadGMOrStaff,
    IsClaimOwnerOrStaff,
    IsClearanceCustodianGM,
    IsClearanceCustodianOrStaff,
    IsClearanceRequesterGM,
    IsContributorOrLeadGMOrStaff,
    IsCrossoverInviteParticipantOrStaff,
    IsCrossoverInviteRecipientOrStaff,
    IsCrossoverInviteSenderOrStaff,
    IsEpisodeStoryOwnerOrStaff,
    IsGlobalProgressReadableOrStaff,
    IsGMProfile,
    IsGroupProgressMemberOrStaff,
    IsLeadGMOfDestinationTableOrStaff,
    IsLeadGMOnClaimStoryOrStaff,
    IsLeadGMOnEpisodeStoryOrStaff,
    IsLeadGMOnStoryOrStaff,
    IsLeadGMOnTransitionStoryOrStaff,
    IsOfferOffererOrStaff,
    IsOfferRecipientGMOrStaff,
    IsParticipationOwnerOrStoryOwnerOrStaff,
    IsPlayerTrustOwnerOrStaff,
    IsProtectedSubjectStoryOwnerOrStaff,
    IsReviewerOrStoryOwnerOrStaff,
    IsSessionRequestGMOrStaff,
    IsSessionRequestParticipantOrStaff,
    IsSignoffOwner,
    IsStaffForCustodyResolution,
    IsStaffOrReadOnly,
    IsStakeBeatStoryOwnerOrStaff,
    IsStakeResolutionBeatStoryOwnerOrStaff,
    IsStakeRewardLineBeatStoryOwnerOrStaff,
    IsStoryGMOfferParticipantOrStaff,
    IsStoryOwnerOrStaff,
    _user_can_read_bulletin_post,
    classify_story_log_viewer_role,
)
from world.stories.serializers import (
    AcceptOfferInputSerializer,
    AggregateBeatContributionSerializer,
    ApproveClaimInputSerializer,
    AssignStoryInputSerializer,
    AssignStoryToTableInputSerializer,
    AssistantGMClaimSerializer,
    BeatCompletionSerializer,
    BeatSerializer,
    CancelClaimInputSerializer,
    CancelSessionRequestInputSerializer,
    ChapterCreateSerializer,
    ChapterDetailSerializer,
    ChapterListSerializer,
    CompleteClaimInputSerializer,
    ContributeBeatInputSerializer,
    CreateBulletinPostInputSerializer,
    CreateBulletinReplyInputSerializer,
    CreateEventFromSessionRequestInputSerializer,
    CrossoverInviteAcceptSerializer,
    CrossoverInviteCreateSerializer,
    CrossoverInviteDeclineSerializer,
    CrossoverInviteSerializer,
    CrossoverInviteWithdrawSerializer,
    CustodyClearanceDecisionInputSerializer,
    CustodyClearanceEscalateInputSerializer,
    CustodyClearanceRequestSerializer,
    CustodyClearanceResolveInputSerializer,
    CustodyClearanceRevokeInputSerializer,
    CustodyClearanceSerializer,
    DeclineOfferInputSerializer,
    EpisodeCreateSerializer,
    EpisodeDetailSerializer,
    EpisodeListSerializer,
    EpisodeProgressionRequirementSerializer,
    EpisodeResolutionSerializer,
    EpisodeSceneSerializer,
    EraSerializer,
    GlobalStoryProgressSerializer,
    GroupStoryProgressSerializer,
    MarkBeatInputSerializer,
    OfferStoryToGMInputSerializer,
    PendingTreasuredSignoffsSerializer,
    PlayerTrustSerializer,
    PromoteEpisodeInputSerializer,
    RejectClaimInputSerializer,
    RequestClaimInputSerializer,
    ResolveEpisodeInputSerializer,
    ResolveForeclosureInputSerializer,
    ResolveSessionRequestInputSerializer,
    ResolveStakeInputSerializer,
    RiskCalibrationSerializer,
    SaveTransitionWithOutcomesInputSerializer,
    SessionRequestSerializer,
    StakeAvailabilitySerializer,
    StakeContractActivationSerializer,
    StakeOutcomeSerializer,
    StakeResolutionSerializer,
    StakeRewardLineSerializer,
    StakeSerializer,
    StakesSummarySerializer,
    StakeTemplateSerializer,
    StoryCreateSerializer,
    StoryDetailSerializer,
    StoryFeedbackCreateSerializer,
    StoryFeedbackSerializer,
    StoryGMOfferSerializer,
    StoryListSerializer,
    StoryLogSerializer,
    StoryNoteSerializer,
    StoryParticipationSerializer,
    StoryProtectedSubjectSerializer,
    TableBulletinPostSerializer,
    TableBulletinReplySerializer,
    TransitionRequiredOutcomeSerializer,
    TransitionSerializer,
    TreasuredSignoffSerializer,
    UpdateBulletinPostInputSerializer,
    UpdateBulletinReplyInputSerializer,
    WithdrawOfferInputSerializer,
    stakes_summary_for_beat,
)
from world.stories.services.custody_clearance import (
    deny_clearance,
    escalate_clearance,
    grant_clearance,
    request_clearance,
    resolve_escalation,
    revoke_clearance,
)
from world.stories.services.dashboards import STALE_STORY_DAYS
from world.stories.services.era import advance_era, archive_era
from world.stories.services.participation import create_story_participation
from world.stories.services.progress import get_active_progress_for_story
from world.stories.services.save_transition import OutcomeInput, save_transition_with_outcomes
from world.stories.services.story_log import serialize_story_log
from world.stories.types import (
    AnyStoryProgress,
    AssignedRequestEntry,
    EligibleTransitionEntry,
    EpisodeReadyEntry,
    FrontierStoryEntry,
    PendingClaimEntry,
    PerGMQueueDepthEntry,
    StaleStoryEntry,
    StoryStatus,
    WaitingForGMEntry,
    WaitingStoryEntry,
)

if TYPE_CHECKING:
    from world.gm.models import GMProfile


class EraViewSet(viewsets.ModelViewSet):
    """ViewSet for Era — metaplot era (season) management.

    Read access: any authenticated user (eras are public metaplot info).
    Write access: staff only.
    Advance/archive actions: staff only (IsAdminUser).

    Wave 11 will register this route; for now urls.py registers it.
    """

    queryset = Era.objects.annotate(story_count=Count("stories_created_in_era"))
    serializer_class = EraSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = EraFilter
    pagination_class = SmallResultsSetPagination
    ordering_fields = ["season_number", "created_at", "status"]
    ordering = ["season_number"]

    def get_permissions(self) -> list[Any]:
        """Read: IsAuthenticated. Write/delete: IsAdminUser."""
        if self.action in {"advance", "archive"} or self.request.method not in (
            "GET",
            "HEAD",
            "OPTIONS",
        ):
            return [permissions.IsAuthenticated(), permissions.IsAdminUser()]
        return [permissions.IsAuthenticated()]

    @action(detail=True, methods=[HTTPMethod.POST])
    def advance(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/eras/{id}/advance/

        Staff-only. Closes the current ACTIVE era; activates this UPCOMING era.
        Returns 200 with updated EraSerializer data, or 400 with detail on error.
        """
        era = self.get_object()
        try:
            updated = advance_era(next_era=era)
        except EraAdvanceError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(EraSerializer(updated, context={"request": request}).data)

    @action(detail=True, methods=[HTTPMethod.POST])
    def archive(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/eras/{id}/archive/

        Staff-only. Marks this era CONCLUDED without advancing to a new one.
        Idempotent for CONCLUDED eras. Returns 200, or 400 with detail on error.
        """
        era = self.get_object()
        try:
            updated = archive_era(era=era)
        except EraAdvanceError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(EraSerializer(updated, context={"request": request}).data)


class StoryViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Story model.
    Provides CRUD operations with proper permissions and filtering.

    Queryset scoping (Phase 5 Task 1.3):
    - Staff: all stories.
    - GM (table owner): all stories at their tables PLUS all owned stories.
    - Authenticated user: stories they own, stories they actively participate in,
      and all GLOBAL-scope stories (publicly browsable).
    - Unauthenticated: none (permission class rejects).

    GROUP-scope stories are visible if the user is an active GMTableMember at the
    story's primary_table AND has an active StoryParticipation.
    """

    queryset = Story.objects.all()
    permission_classes = [IsStoryOwnerOrStaff]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = StoryFilter
    pagination_class = StandardResultsSetPagination
    search_fields = ["title", "description"]
    ordering_fields = ["created_at", "updated_at", "title", "status"]
    ordering = ["-updated_at"]

    def get_queryset(self) -> QuerySet[Story]:
        """Return the scoped story queryset for the requesting user.

        Visibility rules (Phase 5 Task 1.3):
        - Staff: all stories.
        - GM (table owner): all stories at tables they own.
        - CHARACTER-scope: story.character_sheet.character.db_account == user.
        - Participant: active StoryParticipation where character.db_account == user.
        - Story owner (M2M): user in story.owners.
        - GLOBAL scope: visible to all authenticated users (public metaplot).

        The character_sheet path covers personal stories that have no StoryParticipation
        (the story "belongs to" the player by virtue of their character sheet FK).
        """
        qs = super().get_queryset()
        user = self.request.user

        if not user.is_authenticated:
            return qs.none()

        if user.is_staff:
            return qs

        # GM: all stories at tables they own.
        # gm_profile is a reverse OneToOne — not present for non-GM accounts.
        gm_q = models.Q()
        if hasattr(user, "gm_profile"):
            gm_profile = user.gm_profile
            gm_q = models.Q(primary_table__gm=gm_profile)

        # Stories the user owns (by account M2M).
        owned_q = models.Q(owners=user)

        # CHARACTER-scope: story belongs to the user's character sheet.
        # Chain: Story.character_sheet → CharacterSheet.character → ObjectDB.db_account
        character_sheet_q = models.Q(
            scope=StoryScope.CHARACTER,
            character_sheet__character__db_account=user,
        )

        # Stories the user actively participates in (via ObjectDB → db_account).
        participant_q = models.Q(
            participants__character__db_account=user,
            participants__is_active=True,
        )

        # GLOBAL-scope stories are publicly browsable by any authenticated user.
        global_q = models.Q(scope=StoryScope.GLOBAL)

        # PUBLIC-privacy stories are discoverable by any authenticated user — this
        # is required to allow players to find and apply to participate in stories.
        # The existing IsStoryOwnerOrStaff._can_read_story grants PUBLIC stories to
        # all authenticated users; the queryset must match that intent.
        from world.stories.types import StoryPrivacy  # noqa: PLC0415

        public_privacy_q = models.Q(privacy=StoryPrivacy.PUBLIC)

        return qs.filter(
            gm_q | owned_q | character_sheet_q | participant_q | global_q | public_privacy_q
        ).distinct()

    def get_serializer_class(self) -> type[BaseSerializer]:
        """Return appropriate serializer based on action"""
        if self.action == "list":
            return StoryListSerializer
        if self.action == "create":
            return StoryCreateSerializer
        return StoryDetailSerializer

    def perform_create(self, serializer: BaseSerializer) -> None:
        """Set the creator as an owner when creating a story"""
        story = serializer.save()
        story.owners.add(self.request.user)

    @action(detail=True, methods=[HTTPMethod.POST], permission_classes=[CanParticipateInStory])
    def apply_to_participate(self, request: Request, pk: int | None = None) -> Response:
        """Apply to participate in a story"""
        story = self.get_object()
        character_id = request.data.get("character_id")
        participation_level = request.data.get("participation_level", "optional")

        if not character_id:
            return Response(
                {"error": "character_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if already participating
        if StoryParticipation.objects.filter(
            story=story,
            character_id=character_id,
        ).exists():
            return Response(
                {"error": "Already participating in this story"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from evennia.objects.models import ObjectDB  # noqa: PLC0415

        from world.magic.exceptions import ProtagonismLockedError  # noqa: PLC0415

        try:
            character = ObjectDB.objects.get(pk=character_id)
        except ObjectDB.DoesNotExist:
            return Response({"error": "Character not found"}, status=status.HTTP_404_NOT_FOUND)

        try:
            participation = create_story_participation(
                story=story,
                character=character,
                participation_level=participation_level,
            )
        except ProtagonismLockedError as exc:
            return Response({"error": exc.user_message}, status=status.HTTP_403_FORBIDDEN)

        serializer = StoryParticipationSerializer(participation)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=[HTTPMethod.GET])
    def participants(self, request: Request, pk: int | None = None) -> Response:
        """Get all participants for a story"""
        story = self.get_object()
        participants = story.participants.filter(is_active=True)
        serializer = StoryParticipationSerializer(participants, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=[HTTPMethod.GET])
    def chapters(self, request: Request, pk: int | None = None) -> Response:
        """Get all chapters for a story"""
        story = self.get_object()
        chapters = story.chapters.all().order_by("order")
        serializer = ChapterListSerializer(chapters, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=[HTTPMethod.GET], url_path="log")
    def log(self, request: Request, pk: int | None = None) -> Response:
        """GET /api/stories/{id}/log/ — visibility-filtered story log.

        Returns a chronological list of beat completions and episode resolutions
        for this story, filtered to what the viewer is permitted to see:

        - staff: sees all fields including internal_description and gm_notes
        - lead_gm (story.primary_table.gm == request.user.gm_profile): same as staff
        - player (participant / story character owner / active group member): sees
          player-facing text; SECRET beat hints suppressed; no internal fields
        - no_access: 403

        The viewer role is determined by classify_story_log_viewer_role.
        """
        story = self.get_object()
        progress = get_active_progress_for_story(story)
        viewer_role = classify_story_log_viewer_role(request.user, story, progress)
        if viewer_role == VIEWER_ROLE_NO_ACCESS:
            msg = "You do not have access to this story's log."
            raise PermissionDenied(msg)
        log_entries = serialize_story_log(story=story, progress=progress, viewer_role=viewer_role)
        serializer = StoryLogSerializer(log_entries)
        return Response(serializer.data)

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="assign-to-table",
        permission_classes=[IsLeadGMOfDestinationTableOrStaff],
    )
    def assign_to_table(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/stories/{id}/assign-to-table/ — assign a story to a GM's table.

        Lead GM of the destination table (or staff) calls this to take ownership
        of a story. The serializer validates that the caller owns the destination
        table. Returns 200 with the updated Story on success.
        """
        from world.stories.services.tables import assign_story_to_table  # noqa: PLC0415

        story = self.get_object()
        ser = AssignStoryToTableInputSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        updated = assign_story_to_table(story=story, table=ser.validated_data["table"])
        return Response(StoryDetailSerializer(updated, context={"request": request}).data)

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="detach-from-table",
        permission_classes=[CanDetachStoryFromTable],
    )
    def detach_from_table(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/stories/{id}/detach-from-table/ — clear a story's primary_table.

        Allowed by: current Lead GM (story.primary_table.gm), the story's
        character-scope owner (character_sheet.character.db_account == user),
        or staff. Story history and participations are preserved; the story
        enters 'seeking GM' state. Returns 200 with the updated Story.
        """
        from world.stories.services.tables import detach_story_from_table  # noqa: PLC0415

        story = self.get_object()
        updated = detach_story_from_table(story=story)
        return Response(StoryDetailSerializer(updated, context={"request": request}).data)

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="assign-to-scope",
        permission_classes=[IsLeadGMOnStoryOrStaff],
    )
    def assign(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/stories/{id}/assign-to-scope/ — lift a story out of UNASSIGNED.

        Lead GM (story.primary_table.gm) or staff picks the scope and the
        matching target; this sets ``Story.scope`` and creates the
        scope-appropriate progress record so the story can run:

        - CHARACTER: sets ``story.character_sheet`` and creates StoryProgress
        - GROUP: creates GroupStoryProgress for the given gm_table
        - GLOBAL: creates the GlobalStoryProgress singleton

        The scope <-> target invariant is enforced by
        AssignStoryInputSerializer.validate(), so an invalid combination is a
        400 (no scope change, no progress row). Because scope is set before
        the create_*_progress call, StoryNotAssignedError cannot fire — no
        try/except is needed.
        """
        from world.stories.services.progress import (  # noqa: PLC0415
            create_character_progress,
            create_global_progress,
            create_group_progress,
        )

        story = self.get_object()
        ser = AssignStoryInputSerializer(data=request.data, context={"story": story})
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        scope = data["scope"]

        with transaction.atomic():
            story.scope = scope
            if scope == StoryScope.CHARACTER:
                story.character_sheet = data["character_sheet"]
                story.save(update_fields=["scope", "character_sheet"])
                create_character_progress(story=story, character_sheet=data["character_sheet"])
            elif scope == StoryScope.GROUP:
                story.save(update_fields=["scope"])
                create_group_progress(story=story, gm_table=data["gm_table"])
            else:  # StoryScope.GLOBAL
                story.save(update_fields=["scope"])
                create_global_progress(story=story)

        return Response(StoryDetailSerializer(story, context=self.get_serializer_context()).data)

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="send-ooc",
        permission_classes=[permissions.IsAuthenticated, IsStoryLeadGMOrStaff],
    )
    def send_ooc(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/stories/{id}/send-ooc/ — Lead GM or staff sends an OOC notice.

        Body: { body: string, ooc_note?: string }

        Permission: Lead GM of story.primary_table or staff (enforced by
        IsStoryLeadGMOrStaff in permission_classes; has_object_permission fires
        automatically when get_object() is called).
        Input serializer validates body length (>= 1 char).
        Service resolves scope-appropriate recipients and fans out
        NarrativeMessageDelivery rows with category=STORY.

        Returns 201 with the created NarrativeMessage.
        """
        from world.narrative.serializers import (  # noqa: PLC0415
            NarrativeMessageSerializer,
            SendStoryOOCInputSerializer,
        )
        from world.narrative.services import send_story_ooc_message  # noqa: PLC0415

        story = self.get_object()
        ser = SendStoryOOCInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        msg = send_story_ooc_message(
            story=story,
            sender_account=cast(AccountDB, request.user),
            body=ser.validated_data["body"],
            ooc_note=ser.validated_data.get("ooc_note", ""),
        )
        return Response(NarrativeMessageSerializer(msg).data, status=status.HTTP_201_CREATED)

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="offer-to-gm",
        permission_classes=[permissions.IsAuthenticated],
    )
    def offer_to_gm(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/stories/{id}/offer-to-gm/ — player offers their CHARACTER-scope story to a GM.

        Body: { gm_profile_id: number, message?: string }

        The serializer enforces:
        - story.scope == CHARACTER
        - story.primary_table is None
        - story.character_sheet.character.db_account == request.user (or staff)

        Returns 201 with the StoryGMOffer on success.
        """
        from world.stories.services.tables import offer_story_to_gm  # noqa: PLC0415

        story = self.get_object()
        ser = OfferStoryToGMInputSerializer(
            data=request.data, context={"story": story, "request": request}
        )
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        offer = offer_story_to_gm(
            story=story,
            offered_to=data["offered_to"],
            offered_by_account=cast(AccountDB, request.user),
            message=data["message"],
        )
        return Response(StoryGMOfferSerializer(offer).data, status=status.HTTP_201_CREATED)

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="complete",
        permission_classes=[IsLeadGMOnStoryOrStaff],
    )
    def complete(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/stories/{id}/complete/ — conclude a story.

        Lead GM on the story (or staff) marks the story COMPLETED; in-flight
        progress is foreclosed (see complete_story). Idempotent. No request
        body; permission gating is the only access control.
        """
        from world.stories.services.completion import complete_story  # noqa: PLC0415

        story = self.get_object()
        complete_story(story=story)
        serializer = self.get_serializer(story)
        return Response(serializer.data)

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="resolve-foreclosure",
        permission_classes=[IsLeadGMOnStoryOrStaff],
    )
    def resolve_foreclosure(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/stories/{id}/resolve-foreclosure/ — wrap up a foreclosed thread.

        Lead GM on the story (or staff) resolves a FORECLOSED progress record:
        stamps resolved_at/resolved_by and fans out an honest closure message.
        Idempotent. ``resolved_by`` is stamped from the requesting user's
        GMProfile — never accepted from client input.
        """
        from world.gm.models import GMProfile  # noqa: PLC0415
        from world.stories.services.completion import (  # noqa: PLC0415
            resolve_foreclosed_progress,
        )

        story = self.get_object()
        ser = ResolveForeclosureInputSerializer(data=request.data, context={"story": story})
        ser.is_valid(raise_exception=True)
        try:
            gm_profile = request.user.gm_profile
        except GMProfile.DoesNotExist:
            # Staff acting without a GMProfile: the closure still fires; the
            # audit trail is carried by the NarrativeMessage sender_account.
            gm_profile = None
        resolve_foreclosed_progress(progress=ser.validated_data["progress"], resolved_by=gm_profile)
        serializer = self.get_serializer(story)
        return Response(serializer.data)


class StoryParticipationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for StoryParticipation model.
    Manages character participation in stories.
    """

    queryset = StoryParticipation.objects.all()
    serializer_class = StoryParticipationSerializer
    permission_classes = [IsParticipationOwnerOrStoryOwnerOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = StoryParticipationFilter
    pagination_class = StandardResultsSetPagination
    ordering_fields = ["joined_at", "participation_level"]
    ordering = ["-joined_at"]


class ChapterViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Chapter model.
    Manages story chapters with proper story ownership permissions.
    """

    queryset = Chapter.objects.all()
    permission_classes = [IsChapterStoryOwnerOrStaff]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = ChapterFilter
    pagination_class = SmallResultsSetPagination
    search_fields = ["title", "description", "summary"]
    ordering_fields = ["created_at", "order", "title"]
    ordering = ["story", "order"]

    def get_serializer_class(self) -> type[BaseSerializer]:
        """Return appropriate serializer based on action"""
        if self.action == "list":
            return ChapterListSerializer
        if self.action == "create":
            return ChapterCreateSerializer
        return ChapterDetailSerializer

    @action(detail=True, methods=[HTTPMethod.GET])
    def episodes(self, request: Request, pk: int | None = None) -> Response:
        """Get all episodes for a chapter"""
        chapter = self.get_object()
        episodes = chapter.episodes.all().order_by("order")
        serializer = EpisodeListSerializer(episodes, many=True)
        return Response(serializer.data)


class EpisodeViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Episode model.
    Manages story episodes with narrative connection tracking.
    """

    queryset = Episode.objects.all()
    permission_classes = [IsEpisodeStoryOwnerOrStaff]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = EpisodeFilter
    pagination_class = SmallResultsSetPagination
    search_fields = ["title", "description", "summary"]
    ordering_fields = ["created_at", "order", "title"]
    ordering = ["chapter", "order"]

    def get_serializer_class(self) -> type[BaseSerializer]:
        """Return appropriate serializer based on action"""
        if self.action == "list":
            return EpisodeListSerializer
        if self.action == "create":
            return EpisodeCreateSerializer
        return EpisodeDetailSerializer

    @action(detail=True, methods=[HTTPMethod.GET])
    def scenes(self, request: Request, pk: int | None = None) -> Response:
        """Get all scenes for an episode"""
        episode = self.get_object()
        episode_scenes = episode.episode_scenes.all().order_by("order")
        serializer = EpisodeSceneSerializer(episode_scenes, many=True)
        return Response(serializer.data)

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="resolve",
        permission_classes=[IsLeadGMOnStoryOrStaff],
    )
    def resolve(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/episodes/{id}/resolve/ — resolve the current progress for an episode.

        Lead GM or staff posts {progress_id?, chosen_transition?, gm_notes?} to
        advance the story's progress record past the current episode. Returns 201 on success.

        Note: NoEligibleTransitionError and AmbiguousTransitionError can fire from
        resolve_episode() for cases the serializer cannot pre-validate without
        duplicating get_eligible_transitions() logic. These are caught here and
        surfaced as 400 responses. They are genuine runtime errors, not
        user-input-validation errors.
        """
        from world.gm.models import GMProfile  # noqa: PLC0415
        from world.stories.exceptions import StoryError  # noqa: PLC0415
        from world.stories.services.episodes import resolve_episode  # noqa: PLC0415

        episode = self.get_object()
        ser = ResolveEpisodeInputSerializer(data=request.data, context={"episode": episode})
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        try:
            gm_profile = request.user.gm_profile
        except GMProfile.DoesNotExist:
            gm_profile = None

        try:
            resolution = resolve_episode(
                progress=data["progress"],
                chosen_transition=data.get("chosen_transition"),
                gm_notes=data["gm_notes"],
                resolved_by=gm_profile,
            )
        except StoryError as exc:
            # Race condition / service-layer runtime errors:
            # NoEligibleTransitionError — no transitions are eligible (episode frontier).
            # AmbiguousTransitionError — multiple eligible transitions, GM must pick one.
            # These cannot be pre-validated by the serializer without duplicating
            # get_eligible_transitions() logic.
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            EpisodeResolutionSerializer(resolution).data, status=status.HTTP_201_CREATED
        )

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="promote",
        permission_classes=[IsLeadGMOnStoryOrStaff],
    )
    def promote(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/episodes/{id}/promote/ — set the episode's authoring maturity.

        Lead GM or staff posts {target} (a StoryMaturity value). The PLOT-gate
        (resting_conclusion + outbound transition / is_ending) is enforced in
        PromoteEpisodeInputSerializer.validate(), so a violation is a 400.
        Lateral moves and demotions are unvalidated by design.
        """
        from world.stories.services.maturity import (  # noqa: PLC0415
            promote_episode_maturity,
        )

        episode = self.get_object()
        ser = PromoteEpisodeInputSerializer(data=request.data, context={"episode": episode})
        ser.is_valid(raise_exception=True)

        promote_episode_maturity(episode, ser.validated_data["target"])

        return Response(
            EpisodeDetailSerializer(episode, context=self.get_serializer_context()).data
        )


class EpisodeSceneViewSet(viewsets.ModelViewSet):
    """
    ViewSet for EpisodeScene model.
    Manages the connection between episodes and scenes.
    """

    queryset = EpisodeScene.objects.all()
    serializer_class = EpisodeSceneSerializer
    permission_classes = [IsEpisodeStoryOwnerOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = EpisodeSceneFilter
    pagination_class = StandardResultsSetPagination
    ordering_fields = ["order"]
    ordering = ["episode", "order"]


class PlayerTrustViewSet(viewsets.ModelViewSet):
    """
    ViewSet for PlayerTrust model.
    Manages player trust levels for content and GM activities.
    """

    queryset = PlayerTrust.objects.all()
    serializer_class = PlayerTrustSerializer
    permission_classes = [IsPlayerTrustOwnerOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = PlayerTrustFilter
    pagination_class = StandardResultsSetPagination
    ordering_fields = [
        "antagonism_trust",
        "mature_themes_trust",
        "created_at",
        "updated_at",
    ]
    ordering = ["-updated_at"]

    @action(detail=False, methods=[HTTPMethod.GET])
    def my_trust(self, request: Request) -> Response:
        """Get the current user's trust profile"""
        try:
            trust_profile = PlayerTrust.objects.get(
                account=request.user,
            )
            serializer = self.get_serializer(trust_profile)
            return Response(serializer.data)
        except PlayerTrust.DoesNotExist:
            return Response(
                {"error": "Trust profile not found"},
                status=status.HTTP_404_NOT_FOUND,
            )


class StoryFeedbackViewSet(viewsets.ModelViewSet):
    """
    ViewSet for StoryFeedback model.
    Manages feedback on player and GM performance in stories.
    """

    queryset = StoryFeedback.objects.all().order_by(
        "-created_at",
    )
    permission_classes = [IsReviewerOrStoryOwnerOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = StoryFeedbackFilter
    pagination_class = LargeResultsSetPagination
    ordering_fields = ["created_at", "is_positive", "is_gm_feedback"]

    def get_serializer_class(self) -> type[BaseSerializer]:
        """Return appropriate serializer based on action"""
        if self.action == "create":
            return StoryFeedbackCreateSerializer
        return StoryFeedbackSerializer

    def perform_create(self, serializer: BaseSerializer) -> None:
        """Set the reviewer as the current user when creating feedback"""
        serializer.save(reviewer=self.request.user)

    @action(detail=False, methods=[HTTPMethod.GET])
    def my_feedback(self, request: Request) -> Response:
        """Get feedback received by the current user"""
        feedback = self.get_queryset().filter(reviewed_player=request.user)

        # Apply filters manually since we're using a custom queryset
        filterset = self.filterset_class(request.GET, queryset=feedback)
        if filterset.is_valid():
            feedback = filterset.qs

        page = self.paginate_queryset(feedback)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(feedback, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=[HTTPMethod.GET])
    def feedback_given(self, request: Request) -> Response:
        """Get feedback given by the current user"""
        feedback = self.get_queryset().filter(reviewer=request.user)

        # Apply filters manually since we're using a custom queryset
        filterset = self.filterset_class(request.GET, queryset=feedback)
        if filterset.is_valid():
            feedback = filterset.qs

        page = self.paginate_queryset(feedback)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(feedback, many=True)
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# Phase 2 ViewSets
# ---------------------------------------------------------------------------


class GroupStoryProgressViewSet(viewsets.ModelViewSet):
    """ViewSet for GroupStoryProgress — per-GMTable progress pointer.

    Read access: active members of the GMTable.
    Write access: Lead GM (GMTable.gm) and staff.
    """

    queryset = GroupStoryProgress.objects.select_related(
        "story",
        "gm_table",
        "current_episode",
    )
    serializer_class = GroupStoryProgressSerializer
    permission_classes = [IsGroupProgressMemberOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = GroupStoryProgressFilter
    pagination_class = StandardResultsSetPagination
    ordering_fields = ["started_at", "last_advanced_at", "is_active"]
    ordering = ["-last_advanced_at"]

    def get_queryset(self) -> QuerySet[GroupStoryProgress]:
        from world.gm.models import GMProfile  # noqa: PLC0415

        qs = super().get_queryset()
        if self.request.user.is_staff:
            return qs
        try:
            gm_profile = self.request.user.gm_profile
        except GMProfile.DoesNotExist:
            gm_profile = None
        # Active members: Persona -> character_sheet -> character (ObjectDB) -> db_account.
        member_q = models.Q(
            gm_table__memberships__persona__character_sheet__character__db_account=self.request.user,
            gm_table__memberships__left_at__isnull=True,
        )
        # Lead GMs can also see records for their own tables.
        lead_gm_q = models.Q(gm_table__gm=gm_profile) if gm_profile is not None else models.Q()
        return qs.filter(member_q | lead_gm_q).distinct()


class GlobalStoryProgressViewSet(viewsets.ModelViewSet):
    """ViewSet for GlobalStoryProgress — singleton metaplot progress pointer.

    Read access: any authenticated user (metaplot is public).
    Write access: staff only.
    """

    queryset = GlobalStoryProgress.objects.select_related("story", "current_episode")
    serializer_class = GlobalStoryProgressSerializer
    permission_classes = [IsGlobalProgressReadableOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = GlobalStoryProgressFilter
    pagination_class = StandardResultsSetPagination
    ordering_fields = ["started_at", "last_advanced_at", "is_active"]
    ordering = ["-last_advanced_at"]


class AggregateBeatContributionViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only ViewSet for AggregateBeatContribution.

    Writes go through record_aggregate_contribution service (Wave 11 action endpoints).
    Read access: the contributing character's account, story Lead GM (owner), or staff.
    """

    queryset = AggregateBeatContribution.objects.select_related(
        "beat__episode__chapter__story",
        "character_sheet__character",
        "roster_entry",
        "era",
    )
    serializer_class = AggregateBeatContributionSerializer
    permission_classes = [IsContributorOrLeadGMOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = AggregateBeatContributionFilter
    pagination_class = StandardResultsSetPagination
    ordering_fields = ["recorded_at", "points"]
    ordering = ["-recorded_at"]

    def get_queryset(self) -> QuerySet[AggregateBeatContribution]:
        qs = super().get_queryset()
        if self.request.user.is_staff:
            return qs
        # Limit to contributions for characters this user owns, or stories they own
        return qs.filter(
            models.Q(character_sheet__character__db_account=self.request.user)
            | models.Q(beat__episode__chapter__story__owners=self.request.user)
        ).distinct()


class AssistantGMClaimViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for AssistantGMClaim.

    Read: ReadOnlyModelViewSet (list + retrieve).
    State transitions: custom @action endpoints (Wave 11):
      POST /api/assistant-gm-claims/request/ — request_claim
      POST /api/assistant-gm-claims/{id}/approve/ — approve_claim
      POST /api/assistant-gm-claims/{id}/reject/  — reject_claim
      POST /api/assistant-gm-claims/{id}/cancel/  — cancel_claim
      POST /api/assistant-gm-claims/{id}/complete/ — complete_claim

    Read access: the claiming AGM (assistant_gm.account), Lead GM (story owner), or staff.
    """

    queryset = AssistantGMClaim.objects.select_related(
        "beat__episode__chapter__story",
        "assistant_gm__account",
        "approved_by__account",
    )
    serializer_class = AssistantGMClaimSerializer
    permission_classes = [IsClaimantOrLeadGMOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = AssistantGMClaimFilter
    pagination_class = StandardResultsSetPagination
    ordering_fields = ["requested_at", "updated_at", "status"]
    ordering = ["-requested_at"]

    def get_queryset(self) -> QuerySet[AssistantGMClaim]:
        from world.gm.models import GMProfile  # noqa: PLC0415

        qs = super().get_queryset()
        if self.request.user.is_staff:
            return qs
        try:
            gm_profile = self.request.user.gm_profile
        except GMProfile.DoesNotExist:
            gm_profile = None
        filters_q = models.Q(beat__episode__chapter__story__owners=self.request.user)
        if gm_profile is not None:
            filters_q |= models.Q(assistant_gm=gm_profile)
        return qs.filter(filters_q).distinct()

    @action(
        detail=False,
        methods=[HTTPMethod.POST],
        url_path="request",
        permission_classes=[IsGMProfile],
    )
    def request_claim(self, request: Request) -> Response:
        """POST /api/assistant-gm-claims/request/ — an AGM requests to run a beat.

        Requires a GMProfile (enforced by IsGMProfile). Beat existence and
        agm_eligible validation handled by RequestClaimInputSerializer.
        Returns 201 with the claim on success.
        """
        from world.stories.services.assistant_gm import request_claim  # noqa: PLC0415

        ser = RequestClaimInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        claim = request_claim(
            beat=data["beat"],
            assistant_gm=request.user.gm_profile,
            framing_note=data["framing_note"],
        )
        return Response(AssistantGMClaimSerializer(claim).data, status=status.HTTP_201_CREATED)

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="approve",
        permission_classes=[IsGMProfile, IsLeadGMOnClaimStoryOrStaff],
    )
    def approve(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/assistant-gm-claims/{id}/approve/ — Lead GM approves the claim.

        IsGMProfile ensures request.user.gm_profile is always accessible.
        IsLeadGMOnClaimStoryOrStaff confirms Lead GM role on the claim's story.
        Status validation handled by ApproveClaimInputSerializer.
        Returns 200 with the updated claim.
        """
        from world.stories.services.assistant_gm import approve_claim  # noqa: PLC0415

        claim = self.get_object()
        ser = ApproveClaimInputSerializer(data=request.data, context={"claim": claim})
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        updated = approve_claim(
            claim=claim,
            approver=request.user.gm_profile,
            framing_note=data.get("framing_note"),
        )
        return Response(AssistantGMClaimSerializer(updated).data, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="reject",
        permission_classes=[IsGMProfile, IsLeadGMOnClaimStoryOrStaff],
    )
    def reject(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/assistant-gm-claims/{id}/reject/ — Lead GM rejects the claim.

        IsGMProfile ensures request.user.gm_profile is always accessible.
        IsLeadGMOnClaimStoryOrStaff confirms Lead GM role on the claim's story.
        Status validation handled by RejectClaimInputSerializer.
        Returns 200 with the updated claim.
        """
        from world.stories.services.assistant_gm import reject_claim  # noqa: PLC0415

        claim = self.get_object()
        ser = RejectClaimInputSerializer(data=request.data, context={"claim": claim})
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        updated = reject_claim(
            claim=claim,
            approver=request.user.gm_profile,
            note=data["note"],
        )
        return Response(AssistantGMClaimSerializer(updated).data, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="cancel",
        permission_classes=[IsClaimOwnerOrStaff],
    )
    def cancel(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/assistant-gm-claims/{id}/cancel/ — the AGM cancels their own claim.

        Status validation (must be REQUESTED) handled by CancelClaimInputSerializer.
        Returns 200 with the updated claim.
        """
        from world.stories.services.assistant_gm import cancel_claim  # noqa: PLC0415

        claim = self.get_object()
        ser = CancelClaimInputSerializer(data=request.data, context={"claim": claim})
        ser.is_valid(raise_exception=True)

        updated = cancel_claim(claim=claim)
        return Response(AssistantGMClaimSerializer(updated).data, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="complete",
        permission_classes=[IsGMProfile, IsLeadGMOnClaimStoryOrStaff],
    )
    def complete(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/assistant-gm-claims/{id}/complete/ — Lead GM marks an approved claim done.

        IsGMProfile ensures request.user.gm_profile is always accessible.
        IsLeadGMOnClaimStoryOrStaff confirms Lead GM role on the claim's story.
        Status validation (must be APPROVED) handled by CompleteClaimInputSerializer.
        Returns 200 with the updated claim.
        """
        from world.stories.services.assistant_gm import complete_claim  # noqa: PLC0415

        claim = self.get_object()
        ser = CompleteClaimInputSerializer(data=request.data, context={"claim": claim})
        ser.is_valid(raise_exception=True)

        updated = complete_claim(claim=claim, completer=request.user.gm_profile)
        return Response(AssistantGMClaimSerializer(updated).data, status=status.HTTP_200_OK)


class SessionRequestViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for SessionRequest.

    Read: ReadOnlyModelViewSet (list + retrieve).
    State transitions: custom @action endpoints (Wave 11):
      POST /api/session-requests/{id}/create-event/ — create_event_from_session_request
      POST /api/session-requests/{id}/cancel/       — cancel_session_request
      POST /api/session-requests/{id}/resolve/      — resolve_session_request

    Wave 7 auto-creates requests; manual creation is admin-only.
    Read access: players with StoryParticipation, assigned/story-owning GMs, staff.
    """

    queryset = SessionRequest.objects.select_related(
        "episode__chapter__story",
        "event",
        "assigned_gm__account",
        "initiated_by_account",
    )
    serializer_class = SessionRequestSerializer
    permission_classes = [IsSessionRequestParticipantOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = SessionRequestFilter
    pagination_class = StandardResultsSetPagination
    ordering_fields = ["created_at", "updated_at", "status"]
    ordering = ["-created_at"]

    def get_queryset(self) -> QuerySet[SessionRequest]:
        from world.gm.models import GMProfile  # noqa: PLC0415

        qs = super().get_queryset()
        if self.request.user.is_staff:
            return qs
        try:
            gm_profile = self.request.user.gm_profile
        except GMProfile.DoesNotExist:
            gm_profile = None
        filters_q = models.Q(
            episode__chapter__story__participants__character__db_account=self.request.user,
            episode__chapter__story__participants__is_active=True,
        ) | models.Q(episode__chapter__story__owners=self.request.user)
        if gm_profile is not None:
            filters_q |= models.Q(assigned_gm=gm_profile)
        return qs.filter(filters_q).distinct()

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="create-event",
        permission_classes=[IsSessionRequestGMOrStaff],
    )
    def create_event(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/session-requests/{id}/create-event/ — schedule a session by creating an Event.

        Bridges an OPEN SessionRequest to the events system. Status and host_persona
        FK validated by CreateEventFromSessionRequestInputSerializer.
        Returns 201 with the SessionRequest on success.
        """
        from world.stories.services.scheduling import (  # noqa: PLC0415
            create_event_from_session_request,
        )

        session_request = self.get_object()
        ser = CreateEventFromSessionRequestInputSerializer(
            data=request.data, context={"session_request": session_request}
        )
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        create_event_from_session_request(
            session_request=session_request,
            name=data["name"],
            scheduled_real_time=data["scheduled_real_time"],
            host_persona=data["host_persona"],
            location_id=data["location_id"],
            description=data["description"],
            is_public=data["is_public"],
        )
        session_request.refresh_from_db()
        return Response(
            SessionRequestSerializer(session_request).data, status=status.HTTP_201_CREATED
        )

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="cancel",
        permission_classes=[IsSessionRequestGMOrStaff],
    )
    def cancel(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/session-requests/{id}/cancel/ — cancel an OPEN session request.

        Status validation (must be OPEN) handled by CancelSessionRequestInputSerializer.
        Returns 200 with the updated SessionRequest.
        """
        from world.stories.services.scheduling import cancel_session_request  # noqa: PLC0415

        session_request = self.get_object()
        ser = CancelSessionRequestInputSerializer(
            data=request.data, context={"session_request": session_request}
        )
        ser.is_valid(raise_exception=True)

        updated = cancel_session_request(session_request=session_request)
        return Response(SessionRequestSerializer(updated).data, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="resolve",
        permission_classes=[IsSessionRequestGMOrStaff],
    )
    def resolve(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/session-requests/{id}/resolve/ — mark a scheduled session as resolved.

        Status validation (must be SCHEDULED) handled by ResolveSessionRequestInputSerializer.
        Returns 200 with the updated SessionRequest.
        """
        from world.stories.services.scheduling import resolve_session_request  # noqa: PLC0415

        session_request = self.get_object()
        ser = ResolveSessionRequestInputSerializer(
            data=request.data, context={"session_request": session_request}
        )
        ser.is_valid(raise_exception=True)

        updated = resolve_session_request(session_request=session_request)
        return Response(SessionRequestSerializer(updated).data, status=status.HTTP_200_OK)


class BeatViewSet(viewsets.ModelViewSet):
    """ViewSet for Beat — includes all Phase 2 predicate config fields.

    Access delegated to episode story ownership (same as EpisodeViewSet).
    """

    queryset = Beat.objects.select_related(
        "episode__chapter__story__primary_table",  # needed by BeatSerializer.get_can_mark
        "required_achievement",
        "required_condition_template",
        "required_codex_entry",
        "referenced_story",
        "referenced_chapter",
        "referenced_episode",
    )
    serializer_class = BeatSerializer
    permission_classes = [IsBeatStoryOwnerOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = BeatFilter
    pagination_class = StandardResultsSetPagination
    ordering_fields = ["order", "created_at", "updated_at"]
    ordering = ["episode", "order"]

    def get_queryset(self) -> QuerySet[Beat]:
        """Scope the Beat queryset by story read-visibility (#1923).

        ``IsBeatStoryOwnerOrStaff.has_permission`` only checks authentication,
        and DRF's ``list()`` never calls ``has_object_permission`` per row — so
        without a queryset filter any authenticated user could enumerate every
        beat of any episode, including SECRET beats. This mirrors the read
        rule ``IsBeatStoryOwnerOrStaff.has_object_permission`` delegates to
        (``IsStoryOwnerOrStaff._can_read_story``) at the queryset level:

        - Staff: all beats.
        - PUBLIC story: visible to all authenticated users.
        - PRIVATE story: owners or active participants.
        - INVITE_ONLY story: owners or active *trusted* participants.
        - Non-staff viewers never see SECRET beats (matching the story-log
          contract, where SECRET beats surface only on completion for the
          player who completed them).

        ``retrieve``/``update``/etc. still get the real per-object check via
        ``has_object_permission``; this filter only narrows ``list()``.
        """
        from world.stories.types import StoryPrivacy  # noqa: PLC0415

        qs = super().get_queryset()
        user = self.request.user

        if not user.is_authenticated:
            return qs.none()

        if user.is_staff:
            return qs

        # Story FK chain: beat -> episode -> chapter -> story.
        story__ = "episode__chapter__story__"

        # PUBLIC stories are readable by any authenticated user.
        public_q = models.Q(**{f"{story__}privacy": StoryPrivacy.PUBLIC})

        # PRIVATE / INVITE_ONLY: owners ...
        owned_q = models.Q(**{f"{story__}owners": user})

        # ... or active participants. INVITE_ONLY additionally requires
        # trusted_by_owner (mirrors _can_read_story's invite-only branch).
        participant_q = models.Q(
            **{f"{story__}participants__character__db_account": user},
            **{f"{story__}participants__is_active": True},
        )
        trusted_participant_q = participant_q & models.Q(
            **{f"{story__}participants__trusted_by_owner": True},
        )

        private_q = owned_q | participant_q
        invite_only_q = owned_q | trusted_participant_q

        visible_q = (
            public_q
            | (models.Q(**{f"{story__}privacy": StoryPrivacy.PRIVATE}) & private_q)
            | (models.Q(**{f"{story__}privacy": StoryPrivacy.INVITE_ONLY}) & invite_only_q)
        )

        # SECRET beats are never surfaced to non-staff via the list endpoint
        # (matching the story-log contract — they surface only on completion).
        secret_q = models.Q(visibility=BeatVisibility.SECRET)
        visible_q &= ~secret_q

        return qs.filter(visible_q).distinct()

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="mark",
        permission_classes=[CanMarkBeat],
    )
    def mark(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/beats/{id}/mark/ — GM marks the outcome of a GM_MARKED beat.

        Lead GM, staff, or an AGM with an approved claim on this beat may call this.
        Wraps record_gm_marked_outcome. Returns 201 with BeatCompletion on success.
        """
        from world.stories.services.beats import record_gm_marked_outcome  # noqa: PLC0415

        beat = self.get_object()
        ser = MarkBeatInputSerializer(data=request.data, context={"beat": beat})
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        completion = record_gm_marked_outcome(
            progress=data["progress"],
            beat=beat,
            outcome=data["outcome"],
            gm_notes=data["gm_notes"],
            participants=data.get("participants") or None,
            extra_participants=data.get("extra_participants") or None,
        )
        return Response(BeatCompletionSerializer(completion).data, status=status.HTTP_201_CREATED)

    @extend_schema(responses=StakesSummarySerializer)
    @action(
        detail=True,
        methods=[HTTPMethod.GET],
        url_path="stakes-summary",
        permission_classes=[CanViewBeatStakesSummary],
    )
    def stakes_summary(self, request: Request, pk: int | None = None) -> Response:
        """GET /api/beats/{id}/stakes-summary/ — what this beat wagers (#1770 pillar 9).

        Pillar 9 is visibility *at opt-in*, not global enumeration (beats can
        be SECRET; an open wager list leaks GM plans): readable by staff, the
        beat's story owner, or a participant of a scene linked to the beat's
        episode. The payload leaks only player_summary/severity plus
        declared/effective risk and readiness; branch contents
        (StakeResolution rows) are never included.
        """
        beat = self.get_object()
        return Response(stakes_summary_for_beat(beat))

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="contribute",
        permission_classes=[IsAccountOfCharacterSheet],
    )
    def contribute(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/beats/{id}/contribute/ — record a character contribution to an AGGREGATE beat.

        The requesting user must own the character_sheet (or be staff), validated
        by ContributeBeatInputSerializer. Wraps record_aggregate_contribution.
        Returns 201 with contribution on success.
        """
        from world.stories.services.beats import record_aggregate_contribution  # noqa: PLC0415

        beat = self.get_object()
        ser = ContributeBeatInputSerializer(
            data=request.data, context={"beat": beat, "request": request}
        )
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        contribution = record_aggregate_contribution(
            beat=beat,
            character_sheet=data["character_sheet"],
            points=data["points"],
            source_note=data["source_note"],
        )
        return Response(
            AggregateBeatContributionSerializer(contribution).data,
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Wave 3: StoryGMOffer ViewSet
# ---------------------------------------------------------------------------


class StoryGMOfferViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for StoryGMOffer.

    Read: ReadOnlyModelViewSet (list + retrieve).
    State transitions: custom @action endpoints:
      POST /api/story-gm-offers/{id}/accept/   — accept_offer (GM)
      POST /api/story-gm-offers/{id}/decline/  — decline_offer (GM)
      POST /api/story-gm-offers/{id}/withdraw/ — withdraw_offer (player)

    Queryset scoping:
      - Staff: all offers.
      - GM: offers where offered_to.account == user.
      - Player: offers where offered_by_account == user.
    """

    serializer_class = StoryGMOfferSerializer
    permission_classes = [IsStoryGMOfferParticipantOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = StoryGMOfferFilter
    pagination_class = StandardResultsSetPagination
    ordering_fields = ["created_at", "updated_at", "status"]
    ordering = ["-created_at"]

    def get_queryset(self) -> models.QuerySet[StoryGMOffer]:
        user = self.request.user
        if not user.is_authenticated:
            return StoryGMOffer.objects.none()
        if user.is_staff:
            return StoryGMOffer.objects.all()
        from world.gm.models import GMProfile  # noqa: PLC0415

        try:
            gm_profile = user.gm_profile
            gm_q = models.Q(offered_to=gm_profile)
        except GMProfile.DoesNotExist:
            gm_q = models.Q()
        return StoryGMOffer.objects.filter(models.Q(offered_by_account=user) | gm_q).distinct()

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="accept",
        permission_classes=[IsOfferRecipientGMOrStaff],
    )
    def accept(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/story-gm-offers/{id}/accept/ — GM accepts the offer.

        Body: { response_note?: string }

        Assigns story to the GM's first ACTIVE table. Returns 200 with the
        updated StoryGMOffer.
        """
        from world.stories.services.tables import accept_story_offer  # noqa: PLC0415

        offer = self.get_object()
        ser = AcceptOfferInputSerializer(data=request.data, context={"offer": offer})
        ser.is_valid(raise_exception=True)
        # Race-condition guard: the GM may have lost their active table between
        # serializer validation and service execution. Re-raises as 400 to avoid
        # a 500. Matches the EpisodeViewSet.resolve exemption pattern.
        try:
            updated = accept_story_offer(
                offer=offer, response_note=ser.validated_data["response_note"]
            )
        except StoryGMOfferError as exc:
            from rest_framework import serializers as drf_serializers  # noqa: PLC0415

            raise drf_serializers.ValidationError({"non_field_errors": [exc.user_message]}) from exc
        return Response(StoryGMOfferSerializer(updated).data, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="decline",
        permission_classes=[IsOfferRecipientGMOrStaff],
    )
    def decline(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/story-gm-offers/{id}/decline/ — GM declines the offer.

        Body: { response_note?: string }

        Story remains detached. Returns 200 with the updated StoryGMOffer.
        """
        from world.stories.services.tables import decline_story_offer  # noqa: PLC0415

        offer = self.get_object()
        ser = DeclineOfferInputSerializer(data=request.data, context={"offer": offer})
        ser.is_valid(raise_exception=True)
        updated = decline_story_offer(
            offer=offer, response_note=ser.validated_data["response_note"]
        )
        return Response(StoryGMOfferSerializer(updated).data, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="withdraw",
        permission_classes=[IsOfferOffererOrStaff],
    )
    def withdraw(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/story-gm-offers/{id}/withdraw/ — player rescinds the offer.

        No body required. Returns 200 with the updated StoryGMOffer.
        """
        from world.stories.services.tables import withdraw_story_offer  # noqa: PLC0415

        offer = self.get_object()
        ser = WithdrawOfferInputSerializer(data=request.data, context={"offer": offer})
        ser.is_valid(raise_exception=True)
        updated = withdraw_story_offer(offer=offer)
        return Response(StoryGMOfferSerializer(updated).data, status=status.HTTP_200_OK)


class CrossoverInviteViewSet(mixins.CreateModelMixin, viewsets.ReadOnlyModelViewSet):
    """ViewSet for CrossoverInvite — co-GM consent to link stories to a shared event (#2002).

    Read: ReadOnlyModelViewSet (list + retrieve).
    Create: POST /api/crossover-invites/ — any GM may invite another story.
    State transitions: custom @action endpoints:
      POST /api/crossover-invites/{id}/accept/   — invited story's Lead GM
      POST /api/crossover-invites/{id}/decline/   — invited story's Lead GM
      POST /api/crossover-invites/{id}/withdraw/  — inviting GM

    Queryset scoping:
      - Staff: all invites.
      - GM: invites they sent (from_gm.account == user) or received (to_story.owners == user).
    """

    serializer_class = CrossoverInviteSerializer
    permission_classes = [IsCrossoverInviteParticipantOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["event", "to_story", "status", "from_gm"]
    pagination_class = StandardResultsSetPagination
    ordering_fields = ["created_at", "responded_at", "updated_at"]
    ordering = ["-created_at"]

    def get_queryset(self) -> models.QuerySet[CrossoverInvite]:
        user = self.request.user
        if not user.is_authenticated:
            return CrossoverInvite.objects.none()
        if user.is_staff:
            return CrossoverInvite.objects.all()
        return CrossoverInvite.objects.filter(
            models.Q(from_gm__account=user) | models.Q(to_story__owners=user)
        ).distinct()

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """POST /api/crossover-invites/ — create a PENDING crossover invite.

        Body: { event: int, to_story: int, proposed_episode?: int, message?: string }

        The inviting GM is resolved from request.user.gm_profile.
        """
        from world.gm.models import GMProfile  # noqa: PLC0415
        from world.stories.services.crossover import (  # noqa: PLC0415
            CrossoverError,
            create_crossover_invite,
        )

        ser = CrossoverInviteCreateSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        try:
            gm_profile = request.user.gm_profile
        except GMProfile.DoesNotExist:
            return Response(
                {"detail": "You must have a GM profile to send crossover invites."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            invite = create_crossover_invite(
                from_gm=gm_profile,
                event=ser.validated_data["event"],
                to_story=ser.validated_data["to_story"],
                proposed_episode=ser.validated_data.get("proposed_episode"),
                message=ser.validated_data.get("message", ""),
            )
        except CrossoverError as exc:
            raise serializers.ValidationError({"non_field_errors": [str(exc)]}) from exc
        return Response(CrossoverInviteSerializer(invite).data, status=status.HTTP_201_CREATED)

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="accept",
        permission_classes=[IsCrossoverInviteRecipientOrStaff],
    )
    def accept(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/crossover-invites/{id}/accept/ — invited Lead GM accepts.

        Body: { accepted_episode?: int, response_note?: string }

        Creates the EpisodeScene link (immediately if the event has an active
        scene, or deferred to scene-spawn). Enrolls the Lead GM as a scene GM.
        """
        from world.stories.services.crossover import (  # noqa: PLC0415
            CrossoverError,
            accept_crossover_invite,
        )

        invite = self.get_object()
        ser = CrossoverInviteAcceptSerializer(data=request.data, context={"invite": invite})
        ser.is_valid(raise_exception=True)
        try:
            updated = accept_crossover_invite(
                invite=invite,
                accepting_account=cast(AccountDB, request.user),
                accepted_episode=ser.validated_data.get("accepted_episode"),
                response_note=ser.validated_data.get("response_note", ""),
            )
        except CrossoverError as exc:
            raise serializers.ValidationError({"non_field_errors": [str(exc)]}) from exc
        return Response(CrossoverInviteSerializer(updated).data, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="decline",
        permission_classes=[IsCrossoverInviteRecipientOrStaff],
    )
    def decline(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/crossover-invites/{id}/decline/ — invited Lead GM declines.

        Body: { response_note?: string }
        """
        from world.stories.services.crossover import (  # noqa: PLC0415
            CrossoverError,
            decline_crossover_invite,
        )

        invite = self.get_object()
        ser = CrossoverInviteDeclineSerializer(data=request.data, context={"invite": invite})
        ser.is_valid(raise_exception=True)
        try:
            updated = decline_crossover_invite(
                invite=invite,
                responding_account=cast(AccountDB, request.user),
                response_note=ser.validated_data.get("response_note", ""),
            )
        except CrossoverError as exc:
            raise serializers.ValidationError({"non_field_errors": [str(exc)]}) from exc
        return Response(CrossoverInviteSerializer(updated).data, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="withdraw",
        permission_classes=[IsCrossoverInviteSenderOrStaff],
    )
    def withdraw(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/crossover-invites/{id}/withdraw/ — inviting GM rescinds."""
        from world.stories.services.crossover import (  # noqa: PLC0415
            CrossoverError,
            withdraw_crossover_invite,
        )

        invite = self.get_object()
        ser = CrossoverInviteWithdrawSerializer(data=request.data, context={"invite": invite})
        ser.is_valid(raise_exception=True)
        try:
            updated = withdraw_crossover_invite(
                invite=invite,
                withdrawing_account=cast(AccountDB, request.user),
            )
        except CrossoverError as exc:
            raise serializers.ValidationError({"non_field_errors": [str(exc)]}) from exc
        return Response(CrossoverInviteSerializer(updated).data, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Phase 4 Wave 9: Author editor ViewSets
# ---------------------------------------------------------------------------


class TransitionViewSet(viewsets.ModelViewSet):
    """ViewSet for Transition — guarded episode graph edges.

    Read: any authenticated user (Lead GM, players, staff).
    Write (create/update/delete): Lead GM on the source episode's story, or staff.

    The source episode's story is resolved via source_episode -> chapter -> story ->
    primary_table.gm.
    """

    queryset = Transition.objects.select_related(
        "source_episode__chapter__story__primary_table",
        "target_episode",
    )
    serializer_class = TransitionSerializer
    permission_classes = [IsLeadGMOnTransitionStoryOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = TransitionFilter
    pagination_class = StandardResultsSetPagination
    ordering_fields = ["order", "created_at"]
    ordering = ["source_episode", "order"]

    @action(
        detail=False,
        methods=[HTTPMethod.POST],
        url_path="save-with-outcomes",
        permission_classes=[IsLeadGMOnTransitionStoryOrStaff],
    )
    def save_with_outcomes(self, request: Request) -> Response:
        """POST /api/transitions/save-with-outcomes/

        Atomically create or update a Transition and replace its routing
        predicate (TransitionRequiredOutcome) rows in a single transaction.

        Replaces the Phase 4 multi-roundtrip flow:
            POST /api/transitions/  → then N × POST /api/transition-required-outcomes/

        Body::

            {
                "source_episode": <int>,
                "target_episode": <int | null>,
                "mode": "auto" | "gm_choice",
                "connection_type": "" | "therefore" | "but",
                "connection_summary": "<str>",
                "order": <int>,
                "outcomes": [{"beat": <int>, "required_outcome": "success" | "failure" | "expired"},
                             {"beat": <int>, "stake": <int>,
                              "required_stake_column": "win" | "loss" | "withdrawal"},
                             ...],
                "existing_id": <int | null>   # omit or null for create
            }

        Returns the saved Transition (same shape as TransitionSerializer).

        Permissions: Lead GM of source_episode's story, or staff.
        The permission class cannot inspect the object before the serializer runs
        (source_episode comes from the body, not the URL), so this is a view-level
        guard only — any user with a GMProfile who is a Lead GM of *some* story can
        reach this action; the serializer validates that the source_episode's story
        matches the caller.  Stricter object-level gating is applied in
        IsLeadGMOnTransitionStoryOrStaff.has_object_permission after the service
        creates the object — which effectively means the permission class's
        has_permission gate alone guards creation.  This matches the pattern used
        by all other "create with body data" action endpoints in this ViewSet.
        """
        ser = SaveTransitionWithOutcomesInputSerializer(
            data=request.data, context={"request": request}
        )
        ser.is_valid(raise_exception=True)

        vd = ser.validated_data
        existing: Transition | None = vd.get("existing_id")
        source_episode: Episode = vd["source_episode"]

        transition_data: dict[str, Any] = {
            "source_episode": source_episode,
            "target_episode": vd.get("target_episode"),
            "mode": vd["mode"],
            "connection_type": vd.get("connection_type", ""),
            "connection_summary": vd.get("connection_summary", ""),
            "order": vd.get("order", 0),
        }
        outcome_inputs = [
            OutcomeInput(
                beat_id=row["beat"].pk,
                required_outcome=row.get("required_outcome", ""),
                stake_id=row["stake"].pk if row.get("stake") is not None else None,
                required_stake_column=row.get("required_stake_column", ""),
            )
            for row in vd.get("outcomes", [])
        ]

        transition = save_transition_with_outcomes(
            transition_data=transition_data,
            outcomes=outcome_inputs,
            existing_transition=existing,
        )
        out_ser = TransitionSerializer(transition)
        http_status = status.HTTP_200_OK if existing is not None else status.HTTP_201_CREATED
        return Response(out_ser.data, status=http_status)


class EpisodeProgressionRequirementViewSet(viewsets.ModelViewSet):
    """ViewSet for EpisodeProgressionRequirement.

    Records which beats (and required outcomes) must be satisfied before any
    outbound transition fires from an episode.

    Read: any authenticated user.
    Write: Lead GM on the episode's story, or staff.
    """

    queryset = EpisodeProgressionRequirement.objects.select_related(
        "episode__chapter__story__primary_table",
        "beat",
    )
    serializer_class = EpisodeProgressionRequirementSerializer
    permission_classes = [IsLeadGMOnEpisodeStoryOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = EpisodeProgressionRequirementFilter
    pagination_class = StandardResultsSetPagination
    ordering_fields = ["id"]
    ordering = ["episode", "id"]


class TransitionRequiredOutcomeViewSet(viewsets.ModelViewSet):
    """ViewSet for TransitionRequiredOutcome.

    Records which beat outcomes must be satisfied for a specific transition to
    be eligible when the source episode is resolved.

    Read: any authenticated user.
    Write: Lead GM on the transition's source episode's story, or staff.
    """

    queryset = TransitionRequiredOutcome.objects.select_related(
        "transition__source_episode__chapter__story__primary_table",
        "beat",
    )
    serializer_class = TransitionRequiredOutcomeSerializer
    permission_classes = [IsLeadGMOnTransitionStoryOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = TransitionRequiredOutcomeFilter
    pagination_class = StandardResultsSetPagination
    ordering_fields = ["id"]
    ordering = ["transition", "id"]


# ---------------------------------------------------------------------------
# Wave 10: Dashboard APIViews
# ---------------------------------------------------------------------------


class MyActiveStoriesView(APIView):
    """GET /api/stories/my-active/

    Returns the requesting account's active stories across all three scopes
    (CHARACTER / GROUP / GLOBAL), grouped by scope. Each entry carries a
    computed status line summarising what the player should do next.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request) -> Response:
        """Return active stories for the authenticated account."""
        from world.stories.services.dashboards import active_stories_for_account  # noqa: PLC0415

        return Response(active_stories_for_account(request.user))


def _serialize_eligible_transitions(
    transitions: list[Transition],
) -> list[EligibleTransitionEntry]:
    """Serialise eligible Transition objects for GM queue response."""
    return [EligibleTransitionEntry(transition_id=t.pk, mode=t.mode) for t in transitions]


@dataclass
class GMQueueBuckets:
    """Accumulator for the four GMQueue response sections.

    Replaces the six positional list parameters formerly threaded through
    ``_build_gm_queue_for_story``. The field names map 1:1 onto the response
    keys assembled by :class:`GMQueueView`, so the produced JSON is unchanged.
    """

    episodes_ready: list[EpisodeReadyEntry] = field(default_factory=list)
    pending_claims: list[PendingClaimEntry] = field(default_factory=list)
    assigned_requests: list[AssignedRequestEntry] = field(default_factory=list)
    waiting_for_gm: list[WaitingForGMEntry] = field(default_factory=list)


def _eligible_transitions_from_prefetched(
    progress: AnyStoryProgress,
    progression_reqs_by_episode: dict[int, list[EpisodeProgressionRequirement]],
    transitions_by_episode: dict[int, list[Transition]],
) -> list[Transition]:
    """In-memory equivalent of ``get_eligible_transitions`` over prefetched data.

    Mirrors ``world.stories.services.transitions.get_eligible_transitions``
    exactly — same ProgressionRequirementNotMetError semantics, same routing
    predicate (empty required-outcome set is satisfied), same ``order, pk``
    ordering — but consumes maps built from a single batched query pass so it
    issues zero queries per progress. Overdue-beat expiry is performed once,
    in bulk, by the caller before this is invoked (the SharedMemoryModel
    identity map means the in-memory Beat objects walked here already reflect
    any expiry .save()).
    """
    from world.stories.exceptions import ProgressionRequirementNotMetError  # noqa: PLC0415

    episode = progress.current_episode
    if episode is None:
        return []

    # Step 1: every EpisodeProgressionRequirement must be met (else raise).
    for req in progression_reqs_by_episode.get(episode.pk, []):
        if req.beat.outcome != req.required_outcome:
            raise ProgressionRequirementNotMetError

    # Step 2: keep transitions whose routing requirements are all satisfied.
    # cached_required_outcomes was populated via Prefetch(to_attr=...).
    eligible: list[Transition] = []
    for transition in transitions_by_episode.get(episode.pk, []):
        routing = transition.cached_required_outcomes
        if all(r.beat.outcome == r.required_outcome for r in routing):
            eligible.append(transition)
    return eligible


def _expire_overdue_beats_for_episodes(episode_ids: list[int]) -> None:
    """Bulk-detect and expire overdue UNSATISFIED beats across all episodes.

    One query for the whole candidate set (replaces the per-episode SELECT
    that ``get_eligible_transitions`` issued in a loop). Each overdue beat is
    saved individually so the SharedMemoryModel identity-map cache is updated
    in place — a bulk .update() would leave stale Python objects and break the
    subsequent FK walks. The number of saves is bounded by the count of
    actually-overdue beats (data-dependent, typically zero), not by story
    count, so the query bound is preserved.
    """
    if not episode_ids:
        return

    from world.stories.constants import BeatOutcome  # noqa: PLC0415

    now = timezone.now()
    overdue = Beat.objects.filter(
        episode_id__in=episode_ids,
        outcome=BeatOutcome.UNSATISFIED,
        deadline__isnull=False,
        deadline__lt=now,
    )
    for beat in overdue:
        beat.outcome = BeatOutcome.EXPIRED
        beat.save(update_fields=["outcome", "updated_at"])


def _group_progress_by_story(
    manager: Manager,
    story_ids: list[int],
) -> dict[int, list[AnyStoryProgress]]:
    """One batched active-progress query for a scope, grouped by story_id.

    ``order_by("pk")`` makes the per-story order deterministic; the old code
    relied on unspecified DB order and no test asserts progress ordering, so
    the produced set is unchanged.
    """
    by_story: dict[int, list[AnyStoryProgress]] = defaultdict(list)
    if not story_ids:
        return by_story
    qs = (
        manager.filter(story_id__in=story_ids, is_active=True)
        .select_related("current_episode__chapter")
        .order_by("pk")
    )
    for progress in qs:
        by_story[progress.story_id].append(progress)
    return by_story


def _collect_active_progress(
    lead_stories: list[Story],
) -> list[tuple[Story, str, AnyStoryProgress]]:
    """Return (story, progress_type, progress) tuples for all active progress.

    Active progress is fetched in three batched queries (one per scope, over
    all candidate stories at once) instead of one query per story. The result
    is then assembled story-by-story in ``lead_stories`` order so the bucket
    append order is identical to the old per-story loop.
    """
    by_scope = {
        StoryScope.CHARACTER: _group_progress_by_story(
            StoryProgress.objects,
            [s.pk for s in lead_stories if s.scope == StoryScope.CHARACTER],
        ),
        StoryScope.GROUP: _group_progress_by_story(
            GroupStoryProgress.objects,
            [s.pk for s in lead_stories if s.scope == StoryScope.GROUP],
        ),
        StoryScope.GLOBAL: _group_progress_by_story(
            GlobalStoryProgress.objects,
            [s.pk for s in lead_stories if s.scope not in (StoryScope.CHARACTER, StoryScope.GROUP)],
        ),
    }

    rows: list[tuple[Story, str, AnyStoryProgress]] = []
    for story in lead_stories:
        if story.scope == StoryScope.CHARACTER:
            scope = StoryScope.CHARACTER
        elif story.scope == StoryScope.GROUP:
            scope = StoryScope.GROUP
        else:
            scope = StoryScope.GLOBAL
        rows.extend((story, scope, progress) for progress in by_scope[scope].get(story.pk, []))
    return rows


@dataclass
class _GMQueueInputs:
    """Pre-batched lookups consumed by the in-memory bucket assembly.

    Every map is built by exactly one query (or zero when empty), so the
    assembly loop that consumes them issues no queries regardless of how
    many stories the GM leads.
    """

    progress_rows: list[tuple[Story, str, AnyStoryProgress]]
    progression_reqs_by_episode: dict[int, list[EpisodeProgressionRequirement]]
    transitions_by_episode: dict[int, list[Transition]]
    open_request_id_by_episode: dict[int, int]
    claims_by_story: dict[int, list[AssistantGMClaim]]
    assigned_by_story: dict[int, list[SessionRequest]]


def _build_gm_queue_inputs(
    gm_profile: "GMProfile | None",
    lead_stories: list[Story],
) -> _GMQueueInputs:
    """Run the batched query pass for the GM's lead stories.

    Replaces the per-story lookups the old loop issued (eligibility inputs,
    open session requests, pending claims, assigned requests) with one
    query each over the whole candidate set.
    """
    from world.stories.constants import ProgressStatus  # noqa: PLC0415

    story_ids = [s.pk for s in lead_stories]
    progress_rows = _collect_active_progress(lead_stories)

    # Episodes that need eligibility evaluation (skip WAITING_FOR_GM and
    # frontier/null current_episode — those never reach the eligibility path).
    candidate_episode_ids = sorted(
        {
            progress.current_episode_id
            for _story, _ptype, progress in progress_rows
            if progress.status != ProgressStatus.WAITING_FOR_GM
            and progress.current_episode_id is not None
        }
    )

    _expire_overdue_beats_for_episodes(candidate_episode_ids)

    progression_reqs_by_episode: dict[int, list[EpisodeProgressionRequirement]] = defaultdict(list)
    transitions_by_episode: dict[int, list[Transition]] = defaultdict(list)
    open_request_id_by_episode: dict[int, int] = {}
    if candidate_episode_ids:
        for req in EpisodeProgressionRequirement.objects.filter(
            episode_id__in=candidate_episode_ids
        ).select_related("beat"):
            progression_reqs_by_episode[req.episode_id].append(req)

        routing_prefetch = Prefetch(
            "required_outcomes",
            queryset=TransitionRequiredOutcome.objects.select_related("beat"),
            to_attr="cached_required_outcomes",
        )
        for transition in (
            Transition.objects.filter(source_episode_id__in=candidate_episode_ids)
            .prefetch_related(routing_prefetch)
            .order_by("order", "pk")
        ):
            transitions_by_episode[transition.source_episode_id].append(transition)

        # Mirror the old .first() (lowest pk OPEN request per episode):
        # iterate ascending pk and keep the first seen per episode.
        for sr in SessionRequest.objects.filter(
            episode_id__in=candidate_episode_ids,
            status=SessionRequestStatus.OPEN,
        ).order_by("pk"):
            open_request_id_by_episode.setdefault(sr.episode_id, sr.pk)

    claims_by_story: dict[int, list[AssistantGMClaim]] = defaultdict(list)
    for claim in AssistantGMClaim.objects.filter(
        beat__episode__chapter__story_id__in=story_ids,
        status=AssistantClaimStatus.REQUESTED,
    ).select_related("beat", "beat__episode__chapter", "assistant_gm__account"):
        claims_by_story[claim.beat.episode.chapter.story_id].append(claim)

    assigned_by_story: dict[int, list[SessionRequest]] = defaultdict(list)
    for sr in SessionRequest.objects.filter(
        episode__chapter__story_id__in=story_ids,
        assigned_gm=gm_profile,
        status__in=[SessionRequestStatus.OPEN, SessionRequestStatus.SCHEDULED],
    ).select_related("episode__chapter"):
        assigned_by_story[sr.episode.chapter.story_id].append(sr)

    return _GMQueueInputs(
        progress_rows=progress_rows,
        progression_reqs_by_episode=progression_reqs_by_episode,
        transitions_by_episode=transitions_by_episode,
        open_request_id_by_episode=open_request_id_by_episode,
        claims_by_story=claims_by_story,
        assigned_by_story=assigned_by_story,
    )


def _append_progress_row(
    buckets: GMQueueBuckets,
    row: tuple[Story, str, AnyStoryProgress],
    inputs: _GMQueueInputs,
    now: datetime,
) -> None:
    """Assemble one (story, progress_type, progress) row.

    Mirrors the old per-progress branch exactly: WAITING_FOR_GM rows surface
    in waiting_for_gm; null/frontier and ineligible rows are skipped;
    ProgressionRequirementNotMetError skips silently.
    """
    from world.stories.constants import ProgressStatus  # noqa: PLC0415
    from world.stories.exceptions import ProgressionRequirementNotMetError  # noqa: PLC0415

    story, progress_type, progress = row

    if progress.status == ProgressStatus.WAITING_FOR_GM:
        buckets.waiting_for_gm.append(
            {
                "story_id": story.pk,
                "story_title": story.title,
                "scope": story.scope,
                "progress_type": progress_type,
                "progress_id": progress.pk,
                "episode_id": progress.current_episode_id,
                "episode_title": (
                    progress.current_episode.title if progress.current_episode is not None else None
                ),
                "last_advanced_at": progress.last_advanced_at,
                "days_waiting": (now - progress.last_advanced_at).days,
            }
        )
        return
    if progress.current_episode is None:
        return
    try:
        eligible = _eligible_transitions_from_prefetched(
            progress,
            inputs.progression_reqs_by_episode,
            inputs.transitions_by_episode,
        )
    except ProgressionRequirementNotMetError:
        return
    if not eligible:
        return

    episode = progress.current_episode
    buckets.episodes_ready.append(
        {
            "story_id": story.pk,
            "story_title": story.title,
            "scope": story.scope,
            "episode_id": episode.pk,
            "episode_title": episode.title,
            "progress_type": progress_type,
            "progress_id": progress.pk,
            "eligible_transitions": _serialize_eligible_transitions(eligible),
            "open_session_request_id": inputs.open_request_id_by_episode.get(episode.pk),
        }
    )


def _append_story_claims_and_requests(
    buckets: GMQueueBuckets,
    story: Story,
    inputs: _GMQueueInputs,
) -> None:
    """Append a story's pending AGM claims and assigned requests."""
    for claim in inputs.claims_by_story.get(story.pk, []):
        buckets.pending_claims.append(
            {
                "claim_id": claim.pk,
                "beat_id": claim.beat_id,
                "beat_internal_description": claim.beat.internal_description,
                "story_title": story.title,
                "assistant_gm_id": claim.assistant_gm_id,
                "requested_at": claim.requested_at,
            }
        )
    for sr in inputs.assigned_by_story.get(story.pk, []):
        buckets.assigned_requests.append(
            {
                "session_request_id": sr.pk,
                "episode_id": sr.episode_id,
                "episode_title": sr.episode.title,
                "story_title": story.title,
                "status": sr.status,
                "event_id": sr.event_id,
            }
        )


def _collect_gm_queue(gm_profile: "GMProfile | None") -> GMQueueBuckets:
    """Build the GM queue with a bounded number of queries.

    The previous implementation looped over the GM's stories and issued ~8
    queries per story (violating CLAUDE.md "No Queries in Loops"). This hoists
    every per-story lookup into a batched pass keyed on the candidate stories'
    episodes, so the total query count is a small constant independent of how
    many stories the GM leads. The produced buckets are set-identical to the
    old loop's output (response shape/keys/values unchanged); intra-GROUP
    progress is now deterministically pk-ordered where the old ``.first()``
    returned an unspecified DB order, so no test asserts that ordering.
    """
    buckets = GMQueueBuckets()

    # Stories where this GMProfile is Lead GM (via primary_table.gm).
    lead_stories = list(
        Story.objects.filter(
            primary_table__gm=gm_profile,
            status=StoryStatus.ACTIVE,
        ).distinct()
    )
    if not lead_stories:
        return buckets

    inputs = _build_gm_queue_inputs(gm_profile, lead_stories)
    now = timezone.now()

    # Assemble buckets entirely from in-memory maps (zero queries).
    for row in inputs.progress_rows:
        _append_progress_row(buckets, row, inputs, now)

    # AGM claims and assigned requests, story-by-story (same append order).
    for story in lead_stories:
        _append_story_claims_and_requests(buckets, story, inputs)

    return buckets


class GMQueueView(APIView):
    """GET /api/stories/gm-queue/

    Aggregates episodes ready to run across all stories where the requester
    is Lead GM, plus pending AGM claims and assigned SessionRequests.
    """

    permission_classes = [IsGMProfile]

    def get(self, request: Request) -> Response:
        """Return the GM's current work queue."""
        from world.gm.models import GMProfile  # noqa: PLC0415

        try:
            gm_profile = request.user.gm_profile
        except GMProfile.DoesNotExist:
            gm_profile = None

        buckets = _collect_gm_queue(gm_profile)

        return Response(
            {
                "episodes_ready_to_run": buckets.episodes_ready,
                "pending_agm_claims": buckets.pending_claims,
                "assigned_session_requests": buckets.assigned_requests,
                "waiting_for_gm": buckets.waiting_for_gm,
            }
        )


class ExpireOverdueBeatsView(APIView):
    """POST /api/stories/expire-overdue-beats/

    Staff-only trigger that flips all UNSATISFIED beats with past deadlines
    to EXPIRED. Designed for manual triggering and cron hooks.
    Returns {"expired_count": N}.
    """

    permission_classes = [permissions.IsAdminUser]

    def post(self, request: Request) -> Response:
        """Expire all overdue beats and return the count."""
        from world.stories.services.beats import expire_overdue_beats  # noqa: PLC0415

        expired_count = expire_overdue_beats()
        return Response({"expired_count": expired_count}, status=status.HTTP_200_OK)


@dataclass
class _StaffPerGMInputs:
    """Pre-batched lookups for the staff-workload per-GM queue depth.

    Every map is built by exactly one query (or zero when empty), so the
    per-GM / per-story assembly that consumes them issues no queries
    regardless of how many GMs or stories exist. Mirrors the batching
    pattern C1 introduced for the GM queue.
    """

    lead_stories_by_gm: dict[int, list[Story]]
    first_active_progress_by_story: dict[int, AnyStoryProgress]
    progression_reqs_by_episode: dict[int, list[EpisodeProgressionRequirement]]
    transitions_by_episode: dict[int, list[Transition]]
    pending_claims_by_gm: dict[int, int]


def _first_active_progress_by_story(
    lead_stories: list[Story],
) -> dict[int, AnyStoryProgress]:
    """First active progress per story, mirroring get_active_progress_for_story.

    The old per-GM loop called ``get_active_progress_for_story(story)`` once
    per story, which dispatches on scope and returns the first active
    progress (``.first()`` for CHARACTER/GROUP, the OneToOne for GLOBAL,
    ``None`` for UNASSIGNED/other). This reproduces that exactly with three
    batched queries (one per progress model) instead of one query per story.

    The previous ``.first()`` had no ``Meta.ordering``, so which row it
    returned was DB-incidental; ``order_by("pk")`` here deterministically
    stabilises that (same stabilisation C1 applied for the GM queue). No
    staff-workload test asserts which progress row is selected — only the
    integer ``episodes_ready`` count — so the produced response is unchanged.
    """
    by_story: dict[int, AnyStoryProgress] = {}

    char_ids = [s.pk for s in lead_stories if s.scope == StoryScope.CHARACTER]
    if char_ids:
        for progress in (
            StoryProgress.objects.filter(story_id__in=char_ids, is_active=True)
            .select_related("current_episode")
            .order_by("pk")
        ):
            by_story.setdefault(progress.story_id, progress)

    group_ids = [s.pk for s in lead_stories if s.scope == StoryScope.GROUP]
    if group_ids:
        for progress in (
            GroupStoryProgress.objects.filter(story_id__in=group_ids, is_active=True)
            .select_related("current_episode")
            .order_by("pk")
        ):
            by_story.setdefault(progress.story_id, progress)

    global_ids = [s.pk for s in lead_stories if s.scope == StoryScope.GLOBAL]
    if global_ids:
        # GLOBAL is a OneToOne (story.global_progress). The old code returned
        # it regardless of is_active; preserve that (no is_active filter).
        for progress in GlobalStoryProgress.objects.filter(story_id__in=global_ids).select_related(
            "current_episode"
        ):
            by_story.setdefault(progress.story_id, progress)

    # UNASSIGNED / any other scope → no progress (old code returned None).
    return by_story


def _build_staff_per_gm_inputs() -> _StaffPerGMInputs:
    """Run the batched query pass for the staff-workload per-GM section.

    Replaces the per-GM / per-story lookups the old nested loop issued
    (``Story.objects.filter`` per GM, ``get_active_progress_for_story`` per
    story, ``get_eligible_transitions`` per story, ``AssistantGMClaim.count``
    per GM) with a small constant number of batched queries independent of
    the number of GMs and stories.
    """
    # All active lead stories for every qualifying GM, in one query. The old
    # outer query filtered GMs on ``tables__primary_stories__isnull=False``;
    # an active lead story implies such a table, so iterating active lead
    # stories yields exactly the same GM set with the same per-GM story set
    # (the old inner ``Story.objects.filter(primary_table__gm=gm,
    # status="active")``).
    lead_stories_by_gm: dict[int, list[Story]] = defaultdict(list)
    for story in (
        Story.objects.filter(
            primary_table__gm__isnull=False,
            status=StoryStatus.ACTIVE,
        )
        .select_related("primary_table")
        .order_by("pk")
    ):
        lead_stories_by_gm[story.primary_table.gm_id].append(story)

    all_lead_stories = [s for stories in lead_stories_by_gm.values() for s in stories]

    first_active_progress_by_story = _first_active_progress_by_story(all_lead_stories)

    # Episodes that need eligibility evaluation (skip null/frontier — the old
    # code skipped those before calling get_eligible_transitions).
    candidate_episode_ids = sorted(
        {
            progress.current_episode_id
            for progress in first_active_progress_by_story.values()
            if progress.current_episode_id is not None
        }
    )

    _expire_overdue_beats_for_episodes(candidate_episode_ids)

    progression_reqs_by_episode: dict[int, list[EpisodeProgressionRequirement]] = defaultdict(list)
    transitions_by_episode: dict[int, list[Transition]] = defaultdict(list)
    if candidate_episode_ids:
        for req in EpisodeProgressionRequirement.objects.filter(
            episode_id__in=candidate_episode_ids
        ).select_related("beat"):
            progression_reqs_by_episode[req.episode_id].append(req)

        routing_prefetch = Prefetch(
            "required_outcomes",
            queryset=TransitionRequiredOutcome.objects.select_related("beat"),
            to_attr="cached_required_outcomes",
        )
        for transition in (
            Transition.objects.filter(source_episode_id__in=candidate_episode_ids)
            .prefetch_related(routing_prefetch)
            .order_by("order", "pk")
        ):
            transitions_by_episode[transition.source_episode_id].append(transition)

    # Pending AGM claims grouped by lead GM, in one query (replaces the old
    # per-GM ``.count()``). Mirrors the old join
    # ``beat__episode__chapter__story__primary_table__gm=gm``.
    pending_claims_by_gm: dict[int, int] = defaultdict(int)
    for row in (
        AssistantGMClaim.objects.filter(
            status=AssistantClaimStatus.REQUESTED,
            beat__episode__chapter__story__primary_table__gm__isnull=False,
        )
        .values("beat__episode__chapter__story__primary_table__gm")
        .annotate(count=Count("pk"))
    ):
        pending_claims_by_gm[row["beat__episode__chapter__story__primary_table__gm"]] = row["count"]

    return _StaffPerGMInputs(
        lead_stories_by_gm=lead_stories_by_gm,
        first_active_progress_by_story=first_active_progress_by_story,
        progression_reqs_by_episode=progression_reqs_by_episode,
        transitions_by_episode=transitions_by_episode,
        pending_claims_by_gm=pending_claims_by_gm,
    )


def _episodes_ready_for_gm(gm_id: int, inputs: "_StaffPerGMInputs") -> int:
    """Count the active lead stories whose current episode has an eligible transition.

    Pure per-GM arithmetic over the batched inputs (no queries). A story whose
    progress is missing/episode-less, or whose progression requirement is unmet,
    contributes zero.
    """
    from world.stories.exceptions import ProgressionRequirementNotMetError  # noqa: PLC0415

    episodes_ready_count = 0
    for story in inputs.lead_stories_by_gm.get(gm_id, []):
        progress = inputs.first_active_progress_by_story.get(story.pk)
        if progress is None or progress.current_episode is None:
            continue
        try:
            eligible = _eligible_transitions_from_prefetched(
                progress,
                inputs.progression_reqs_by_episode,
                inputs.transitions_by_episode,
            )
        except ProgressionRequirementNotMetError:
            continue
        if eligible:
            episodes_ready_count += 1
    return episodes_ready_count


def _collect_per_gm_queue_depth() -> list[PerGMQueueDepthEntry]:
    """Assemble the per-GM queue depth section from batched inputs.

    Iterates the *status-agnostic* GM membership set — exactly the pre-C2
    ``GMProfile.objects.filter(tables__primary_stories__isnull=False).distinct()``
    (``Story.primary_table`` reverse = ``primary_stories``; ``GMTable.gm``
    reverse = ``tables``; NO ``status`` filter). A GM whose only primary
    story is non-active (INACTIVE — the model default — / COMPLETED /
    CANCELLED) was emitted by the pre-C2 code with ``episodes_ready=0`` and
    any (status-agnostic) ``pending_claims``; the C2 bounding refactor
    narrowed this to GMs with an *active* lead story and silently dropped
    those GMs. Restoring the wide membership set here makes the output
    byte-identical to pre-C2 again: same per-GM dict keys in the same
    order, same ``episodes_ready`` count, same ``pending_claims`` count.
    The per-GM arithmetic is unchanged (active lead stories still drive
    ``episodes_ready``; ``pending_claims_by_gm`` is already
    status-agnostic). GM iteration order is by ``GMProfile.pk`` (the old
    code iterated a ``GMProfile`` queryset with no ``Meta.ordering`` —
    DB-incidental; deterministically stabilised here; no test asserts
    per-GM ordering). Still O(1) queries: the membership set + account
    preload is exactly one extra query independent of N.
    """
    from world.gm.models import GMProfile  # noqa: PLC0415

    inputs = _build_staff_per_gm_inputs()

    # Status-agnostic GM membership set, verbatim pre-C2 derivation (one
    # query; account preloaded for username). Widening this filter to the
    # status-agnostic set — rather than restricting to the active-lead-story
    # GM ids — is the entire fix; the per-GM arithmetic below is untouched.
    gm_by_id = {
        gm.pk: gm
        for gm in GMProfile.objects.select_related("account")
        .filter(tables__primary_stories__isnull=False)
        .distinct()
    }
    gm_ids = sorted(gm_by_id.keys())
    if not gm_ids:
        return []

    per_gm_queue: list[PerGMQueueDepthEntry] = []
    for gm_id in gm_ids:
        gm = gm_by_id.get(gm_id)
        if gm is None:
            continue
        episodes_ready_count = _episodes_ready_for_gm(gm_id, inputs)

        per_gm_queue.append(
            {
                "gm_profile_id": gm.pk,
                "gm_name": gm.account.username,
                "episodes_ready": episodes_ready_count,
                "pending_claims": inputs.pending_claims_by_gm.get(gm_id, 0),
            }
        )
    return per_gm_queue


class StaffWorkloadView(APIView):
    """GET /api/stories/staff-workload/

    Staff-only cross-story metrics: per-GM queue depth, stale stories,
    stories at the authoring frontier, and aggregate counts.

    Performance: the per-GM queue depth is computed with a constant number
    of batched queries (see ``_collect_per_gm_queue_depth``) independent of
    the number of GMs/stories/progress rows. The stale / waiting-for-GM /
    frontier sections are genuine wire aggregations — one ``.values()`` scan
    per progress model (a fixed three queries each), not per-row queries.
    """

    permission_classes = [permissions.IsAdminUser]

    def get(self, request: Request) -> Response:
        """Return cross-story workload metrics for staff."""
        from world.stories.constants import ProgressStatus  # noqa: PLC0415

        # --- per-GM queue depth (bounded: see _collect_per_gm_queue_depth) ---
        per_gm_queue = _collect_per_gm_queue_depth()

        # --- stale stories ---
        cutoff = timezone.now() - timezone.timedelta(days=STALE_STORY_DAYS)
        stale_qs = (
            list(
                StoryProgress.objects.filter(
                    is_active=True,
                    last_advanced_at__lt=cutoff,
                )
                .select_related("story")
                .values("story__id", "story__title", "last_advanced_at")
            )
            + list(
                GroupStoryProgress.objects.filter(
                    is_active=True,
                    last_advanced_at__lt=cutoff,
                )
                .select_related("story")
                .values("story__id", "story__title", "last_advanced_at")
            )
            + list(
                GlobalStoryProgress.objects.filter(
                    is_active=True,
                    last_advanced_at__lt=cutoff,
                )
                .select_related("story")
                .values("story__id", "story__title", "last_advanced_at")
            )
        )

        now = timezone.now()
        stale_stories: list[StaleStoryEntry] = [
            StaleStoryEntry(
                story_id=row["story__id"],
                story_title=row["story__title"],
                last_advanced_at=row["last_advanced_at"],
                days_stale=(now - row["last_advanced_at"]).days,
            )
            for row in stale_qs
        ]

        # --- stories waiting on a GM (any age — a fresh dropped ball is
        # still a dropped ball; staleness is reported separately above) ---
        waiting_qs = (
            list(
                StoryProgress.objects.filter(
                    is_active=True,
                    status=ProgressStatus.WAITING_FOR_GM,
                )
                .select_related("story")
                .values("story__id", "story__title", "story__scope", "last_advanced_at")
            )
            + list(
                GroupStoryProgress.objects.filter(
                    is_active=True,
                    status=ProgressStatus.WAITING_FOR_GM,
                )
                .select_related("story")
                .values("story__id", "story__title", "story__scope", "last_advanced_at")
            )
            + list(
                GlobalStoryProgress.objects.filter(
                    is_active=True,
                    status=ProgressStatus.WAITING_FOR_GM,
                )
                .select_related("story")
                .values("story__id", "story__title", "story__scope", "last_advanced_at")
            )
        )
        stories_waiting_for_gm: list[WaitingStoryEntry] = [
            WaitingStoryEntry(
                story_id=row["story__id"],
                story_title=row["story__title"],
                scope=row["story__scope"],
                last_advanced_at=row["last_advanced_at"],
                days_waiting=(now - row["last_advanced_at"]).days,
            )
            for row in waiting_qs
        ]

        # --- stories at frontier (current_episode is None but active) ---
        frontier_char = list(
            StoryProgress.objects.filter(
                is_active=True,
                current_episode__isnull=True,
            )
            .select_related("story")
            .values("story__id", "story__title", "story__scope")
        )
        frontier_group = list(
            GroupStoryProgress.objects.filter(
                is_active=True,
                current_episode__isnull=True,
            )
            .select_related("story")
            .values("story__id", "story__title", "story__scope")
        )
        frontier_global = list(
            GlobalStoryProgress.objects.filter(
                is_active=True,
                current_episode__isnull=True,
            )
            .select_related("story")
            .values("story__id", "story__title", "story__scope")
        )
        stories_at_frontier: list[FrontierStoryEntry] = [
            FrontierStoryEntry(
                story_id=row["story__id"],
                story_title=row["story__title"],
                scope=row["story__scope"],
            )
            for row in frontier_char + frontier_group + frontier_global
        ]

        # --- aggregate counts ---
        pending_agm_count = AssistantGMClaim.objects.filter(
            status=AssistantClaimStatus.REQUESTED,
        ).count()

        open_session_req_count = SessionRequest.objects.filter(
            status=SessionRequestStatus.OPEN,
        ).count()

        counts_by_scope_qs = Story.objects.values("scope").annotate(count=Count("pk"))
        counts_by_scope: dict[str, int] = {row["scope"]: row["count"] for row in counts_by_scope_qs}

        return Response(
            {
                "per_gm_queue_depth": per_gm_queue,
                "stale_stories": stale_stories,
                "stories_waiting_for_gm": stories_waiting_for_gm,
                "stories_at_frontier": stories_at_frontier,
                "pending_agm_claims_count": pending_agm_count,
                "open_session_requests_count": open_session_req_count,
                "counts_by_scope": counts_by_scope,
            }
        )


# ---------------------------------------------------------------------------
# StoryNote ViewSet (append-only OOC authorial memory)
# ---------------------------------------------------------------------------


class StoryNoteViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """Append-only StoryNote API — list, retrieve, and create only.

    StoryNote is OOC authorial memory: never plain-player-visible, and never
    editable or deletable. Omitting the update/destroy mixins makes PATCH and
    DELETE return 405. Access is gated by CanAccessStoryNotes (staff, story
    owner, or active/Lead GM of the story).
    """

    queryset = (
        StoryNote.objects.select_related("story", "author_account").all().order_by("-created_at")
    )
    serializer_class = StoryNoteSerializer
    permission_classes = [permissions.IsAuthenticated, CanAccessStoryNotes]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = StoryNoteFilter
    pagination_class = StandardResultsSetPagination
    ordering_fields = ["created_at"]
    ordering = ["-created_at"]

    def get_queryset(self) -> QuerySet[StoryNote]:
        """Scope the queryset to notes the requesting user may access.

        Defense-in-depth mirroring AggregateBeatContributionViewSet /
        TableBulletinPostViewSet: staff see all; everyone else is scoped to
        stories they own, actively GM, or Lead-GM via the primary table.
        The optional ``story`` filterset further-narrows this safe queryset.
        """
        from world.gm.models import GMProfile  # noqa: PLC0415

        qs = super().get_queryset()
        user = self.request.user
        if user.is_staff:
            return qs

        # Stories the user owns (account M2M) — mirrors StoryViewSet owned_q
        # (views.py:294 ``models.Q(owners=user)``) with a story__ prefix.
        access_q = models.Q(story__owners=user)

        # Active GM / Lead GM of the story's primary table — mirrors
        # AssistantGMClaimViewSet (views.py:923 ``models.Q(assistant_gm=gm_profile)``)
        # and StoryViewSet gm_q (views.py:291 ``models.Q(primary_table__gm=gm_profile)``)
        # with a story__ prefix.
        try:
            gm_profile = user.gm_profile
            access_q |= models.Q(story__active_gms=gm_profile) | models.Q(
                story__primary_table__gm=gm_profile
            )
        except GMProfile.DoesNotExist:
            pass

        return qs.filter(access_q).distinct()


# ---------------------------------------------------------------------------
# Wave 10: TableBulletin ViewSets
# ---------------------------------------------------------------------------


class TableBulletinPostViewSet(viewsets.ModelViewSet):
    """ViewSet for TableBulletinPost — bulletin posts on GMTables.

    Read access: Lead GM / staff (always) + active table members (table-wide
    posts) or story participants (story-scoped posts).
    Create: Lead GM of the target table or staff.
    Update/Delete: Lead GM of the post's table or staff.
    """

    queryset = TableBulletinPost.objects.select_related(
        "table__gm",
        "story",
        "author_persona",
    ).prefetch_related(
        models.Prefetch(
            "replies",
            queryset=TableBulletinReply.objects.select_related("author_persona"),
            to_attr="replies_cached",
        ),
    )
    serializer_class = TableBulletinPostSerializer
    permission_classes = [CanAuthorBulletinPost]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = TableBulletinPostFilter
    pagination_class = StandardResultsSetPagination
    ordering_fields = ["created_at", "updated_at"]
    ordering = ["-created_at"]

    def get_queryset(self) -> QuerySet[TableBulletinPost]:
        """Scope the queryset to posts the requesting user may read."""
        from world.gm.models import GMProfile  # noqa: PLC0415

        qs = super().get_queryset()
        user = self.request.user
        if user.is_staff:
            return qs

        # Lead GM of any table — sees all posts on their tables.
        lead_gm_q = models.Q()
        try:
            gm_profile = user.gm_profile
            lead_gm_q = models.Q(table__gm=gm_profile)
        except GMProfile.DoesNotExist:
            pass

        # Active table member — sees table-wide posts (story=None).
        active_member_table_wide_q = models.Q(
            table__memberships__persona__character_sheet__character__db_account=user,
            table__memberships__left_at__isnull=True,
            story__isnull=True,
        )

        # Active story participant — sees story-scoped posts for their stories.
        active_participant_q = models.Q(
            story__participants__character__db_account=user,
            story__participants__is_active=True,
        )

        return qs.filter(lead_gm_q | active_member_table_wide_q | active_participant_q).distinct()

    def get_serializer_class(self) -> type[BaseSerializer]:
        """Use input serializers for write operations."""
        if self.action == "create":
            return CreateBulletinPostInputSerializer
        if self.action in {"update", "partial_update"}:
            return UpdateBulletinPostInputSerializer
        return TableBulletinPostSerializer

    def get_object(self) -> TableBulletinPost:
        """Standard get_object with read permission check."""
        obj = super().get_object()
        # For retrieve, ensure the user can actually read this post.
        if self.action == "retrieve":
            if not _user_can_read_bulletin_post(self.request.user, obj):
                msg = "You do not have permission to view this bulletin post."
                raise PermissionDenied(msg)
        return obj

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Create a bulletin post using the three-layer pattern."""
        from world.stories.services.bulletin import create_bulletin_post  # noqa: PLC0415

        ser = CreateBulletinPostInputSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data
        post = create_bulletin_post(
            table=vd["table"],
            author_persona=vd["author_persona"],
            title=vd["title"],
            body=vd["body"],
            story=vd.get("story"),
            allow_replies=vd.get("allow_replies", True),
        )
        return Response(TableBulletinPostSerializer(post).data, status=status.HTTP_201_CREATED)

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Edit a post (author / staff)."""
        from world.stories.services.bulletin import edit_bulletin_post  # noqa: PLC0415

        post = self.get_object()
        self.check_object_permissions(request, post)
        ser = UpdateBulletinPostInputSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data
        edit_bulletin_post(
            post=post,
            title=vd.get("title"),
            body=vd.get("body"),
            allow_replies=vd.get("allow_replies"),
        )
        return Response(TableBulletinPostSerializer(post).data)

    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Delegate to update (always partial for this viewset)."""
        return self.update(request, *args, **kwargs)

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Delete a post (author / staff)."""
        from world.stories.services.bulletin import delete_bulletin_post  # noqa: PLC0415

        post = self.get_object()
        self.check_object_permissions(request, post)
        delete_bulletin_post(post=post)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TableBulletinReplyViewSet(viewsets.ModelViewSet):
    """ViewSet for TableBulletinReply — replies to bulletin posts.

    Read access: same as the parent post (reader must have read access to post).
    Create: any qualifying reader when post.allow_replies=True (staff bypass).
    Update/Delete: reply author or staff.
    """

    queryset = TableBulletinReply.objects.select_related(
        "post__table__gm",
        "post__story",
        "author_persona__character_sheet__character",  # needed by IsBulletinReplyAuthorOrStaff
    )
    serializer_class = TableBulletinReplySerializer
    permission_classes = [CanReplyToBulletinPost]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = TableBulletinReplyFilter
    pagination_class = StandardResultsSetPagination
    ordering_fields = ["created_at"]
    ordering = ["created_at"]

    def get_queryset(self) -> QuerySet[TableBulletinReply]:
        """Scope to replies whose parent post the user may read."""
        from world.gm.models import GMProfile  # noqa: PLC0415

        qs = super().get_queryset()
        user = self.request.user
        if user.is_staff:
            return qs

        lead_gm_q = models.Q()
        try:
            gm_profile = user.gm_profile
            lead_gm_q = models.Q(post__table__gm=gm_profile)
        except GMProfile.DoesNotExist:
            pass

        active_member_table_wide_q = models.Q(
            post__table__memberships__persona__character_sheet__character__db_account=user,
            post__table__memberships__left_at__isnull=True,
            post__story__isnull=True,
        )
        active_participant_q = models.Q(
            post__story__participants__character__db_account=user,
            post__story__participants__is_active=True,
        )

        return qs.filter(lead_gm_q | active_member_table_wide_q | active_participant_q).distinct()

    def get_permissions(self) -> list[Any]:
        """Create: CanReplyToBulletinPost (read + allow_replies check in serializer).
        Update/partial_update/destroy: IsBulletinReplyAuthorOrStaff (author or staff).
        All others: base CanReplyToBulletinPost.
        """
        if self.action in {"update", "partial_update", "destroy"}:
            return [IsBulletinReplyAuthorOrStaff()]
        return [CanReplyToBulletinPost()]

    def get_serializer_class(self) -> type[BaseSerializer]:
        if self.action == "create":
            return CreateBulletinReplyInputSerializer
        if self.action in {"update", "partial_update"}:
            return UpdateBulletinReplyInputSerializer
        return TableBulletinReplySerializer

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Create a reply using the three-layer pattern."""
        from world.stories.services.bulletin import reply_to_post  # noqa: PLC0415

        ser = CreateBulletinReplyInputSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data
        reply = reply_to_post(
            post=vd["post"],
            author_persona=vd["author_persona"],
            body=vd["body"],
        )
        return Response(TableBulletinReplySerializer(reply).data, status=status.HTTP_201_CREATED)

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Edit a reply — IsBulletinReplyAuthorOrStaff enforces author ownership."""
        reply = self.get_object()
        ser = UpdateBulletinReplyInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        reply.body = ser.validated_data["body"]
        reply.save(update_fields=["body"])
        return Response(TableBulletinReplySerializer(reply).data)

    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Delegate to update."""
        return self.update(request, *args, **kwargs)

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Delete a reply — IsBulletinReplyAuthorOrStaff enforces author ownership."""
        reply = self.get_object()
        reply.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# #1770 PR1: Stakes-contract engine ViewSets
# ---------------------------------------------------------------------------


class RiskCalibrationViewSet(viewsets.ModelViewSet):
    """ViewSet for RiskCalibration — staff-tunable calibration bands (#1770 pillar 5)."""

    queryset = RiskCalibration.objects.all()
    serializer_class = RiskCalibrationSerializer
    permission_classes = [IsStaffOrReadOnly]
    filter_backends = [filters.OrderingFilter]
    pagination_class = StandardResultsSetPagination
    ordering_fields = ["risk"]
    ordering = ["risk"]


class StakeTemplateViewSet(viewsets.ModelViewSet):
    """ViewSet for StakeTemplate — the GM-facing stake catalog (#1770 pillar 5)."""

    queryset = StakeTemplate.objects.all()
    serializer_class = StakeTemplateSerializer
    permission_classes = [IsStaffOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = StakeTemplateFilter
    pagination_class = StandardResultsSetPagination
    ordering_fields = ["subject_kind", "severity", "name"]
    ordering = ["subject_kind", "severity", "name"]


class StakeViewSet(viewsets.ModelViewSet):
    """ViewSet for Stake (#1770 pillar 1).

    Access delegated to beat story ownership via obj.beat, same chain as
    BeatViewSet (beat -> episode -> chapter -> story).
    """

    queryset = Stake.objects.select_related(
        "beat",
        "template",
        "subject_sheet",
        "subject_item",
        "subject_society",
        "subject_organization",
        # DRF's nested StakeOutcomeSerializer reads the related manager, so the
        # prefetch must populate the default cache (to_attr would be unused).
    ).prefetch_related("outcomes")  # noqa: PREFETCH_STRING
    serializer_class = StakeSerializer
    permission_classes = [IsStakeBeatStoryOwnerOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = StakeFilter
    pagination_class = StandardResultsSetPagination
    ordering_fields = ["severity", "created_at", "updated_at"]
    ordering = ["beat", "-severity", "pk"]

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="resolve",
        permission_classes=[CanResolveStake],
    )
    def resolve(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/stakes/{id}/resolve/ — GM constrained pick (#1770 PR2).

        Lead GM, staff, or an AGM with an approved claim on the stake's beat
        picks one of the stake's AUTHORED resolution columns; the branch fires
        exactly like the machine path (pool + writers) and the StakeOutcome
        audit row records method=GM_PICK with the GM and notes. Optional
        ``participants`` / ``extra_participants`` carry the personas the
        branch's pool and affection writer credit (MarkBeat semantics).
        Returns 201 with the StakeOutcome.

        The LEGEND_AWARD participant guards fire inside the service's pool
        walk — pre-validating them in the serializer would duplicate
        resolve_pool_consequences; they are surfaced as 400 here (same
        exception-block carve-out as EpisodeViewSet.resolve).
        """
        from world.gm.models import GMProfile  # noqa: PLC0415
        from world.societies.exceptions import (  # noqa: PLC0415
            LegendAwardParticipantMissingError,
            LegendAwardScopeError,
        )
        from world.stories.services.stake_resolution import (  # noqa: PLC0415
            resolve_stake_by_gm_pick,
        )

        stake = self.get_object()
        ser = ResolveStakeInputSerializer(data=request.data, context={"stake": stake})
        ser.is_valid(raise_exception=True)

        try:
            gm_profile = request.user.gm_profile
        except GMProfile.DoesNotExist:
            gm_profile = None

        try:
            outcome = resolve_stake_by_gm_pick(
                stake,
                column=ser.validated_data["column"],
                outcome_key=ser.validated_data.get("outcome_key", ""),
                gm_profile=gm_profile,
                gm_notes=ser.validated_data["gm_notes"],
                participants=ser.validated_data.get("participants") or None,
                extra_participants=ser.validated_data.get("extra_participants") or None,
            )
        except (LegendAwardParticipantMissingError, LegendAwardScopeError) as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(StakeOutcomeSerializer(outcome).data, status=status.HTTP_201_CREATED)


class StakeResolutionViewSet(viewsets.ModelViewSet):
    """ViewSet for StakeResolution (#1770 pillar 1).

    Access delegated to the parent stake's beat story ownership via
    obj.stake.beat.
    """

    queryset = StakeResolution.objects.select_related(
        "stake__beat",
        "consequence_pool",
        # DRF's nested StakeRewardLineSerializer reads the related manager, so
        # the prefetch must populate the default cache (to_attr would be unused).
    ).prefetch_related("reward_lines")  # noqa: PREFETCH_STRING
    serializer_class = StakeResolutionSerializer
    permission_classes = [IsStakeResolutionBeatStoryOwnerOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = StakeResolutionFilter
    pagination_class = StandardResultsSetPagination
    ordering_fields = ["column"]
    ordering = ["stake", "column"]


class StakeRewardLineViewSet(viewsets.ModelViewSet):
    """ViewSet for StakeRewardLine (#1770 PR3 — the contract's win side).

    Access delegated to the parent resolution's stake's beat story ownership
    via obj.resolution.stake.beat — the same walk as StakeResolutionViewSet,
    one hop deeper. The serializer enforces the create-path ownership gate,
    the open-activation lock, and the sink/resonance shape.
    """

    queryset = StakeRewardLine.objects.select_related(
        "resolution__stake__beat",
        "resonance",
    )
    serializer_class = StakeRewardLineSerializer
    permission_classes = [IsStakeRewardLineBeatStoryOwnerOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = StakeRewardLineFilter
    pagination_class = StandardResultsSetPagination
    ordering_fields = ["amount"]
    ordering = ["resolution", "pk"]


class StakeContractActivationViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only ViewSet for StakeContractActivation — the lock/audit surface
    (#1770 pillars 7-8)."""

    queryset = StakeContractActivation.objects.select_related("beat")
    serializer_class = StakeContractActivationSerializer
    permission_classes = [IsStakeBeatStoryOwnerOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = StakeContractActivationFilter
    pagination_class = StandardResultsSetPagination
    ordering_fields = ["locked_at"]
    ordering = ["-locked_at"]


# ---------------------------------------------------------------------------
# #1771 task 6: sign-off grant/withdraw + GM stake-availability
#
# These operate on stories-owned models (Beat, TreasuredSignoff) and call
# world.stories.services.boundaries — living here (not world.boundaries.views)
# keeps that app free of a world.stories import (ADR-0010 FK direction
# specific->general; stories depends on boundaries, never the reverse). See
# world/stories/serializers.py's matching comment on TreasuredSignoffSerializer
# / StakeAvailabilitySerializer, and Task 5's identical call for the
# underlying service functions.
# ---------------------------------------------------------------------------


class TreasuredSignoffViewSet(viewsets.ModelViewSet):
    """ViewSet for a player's own pre-scene ``TreasuredSignoff`` grants (#1771).

    Self-authored consent: ``get_queryset`` scopes to the requesting
    player's own sign-offs. ``create()`` grants (or reactivates) via
    ``grant_treasured_signoff``; the ``withdraw`` action soft-withdraws via
    ``withdraw_treasured_signoff``. Never hard-deletes (``destroy`` is not
    exposed) — story-significant data, per repo convention.
    """

    http_method_names = ["get", "post", "head", "options"]
    serializer_class = TreasuredSignoffSerializer
    permission_classes = [IsSignoffOwner]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["beat", "treasured_subject"]
    pagination_class = StandardResultsSetPagination
    ordering = ["beat", "pk"]

    def get_queryset(self) -> QuerySet[TreasuredSignoff]:
        """Scope queryset to the requesting player's own sign-offs."""
        try:
            return TreasuredSignoff.objects.filter(
                player_data=self.request.user.player_data,
            ).order_by("beat", "pk")
        except AttributeError:
            return TreasuredSignoff.objects.none()

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Grant (or reactivate) a sign-off via ``grant_treasured_signoff``."""
        from world.stories.services.boundaries import grant_treasured_signoff  # noqa: PLC0415

        if not hasattr(request.user, "player_data"):
            raise PermissionDenied
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        player_data = cast(PlayerData, request.user.player_data)
        signoff = grant_treasured_signoff(
            beat=serializer.validated_data["beat"],
            player_data=player_data,
            treasured_subject=serializer.validated_data["treasured_subject"],
        )
        output = self.get_serializer(signoff)
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=[HTTPMethod.POST])
    def withdraw(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/treasured-signoffs/{id}/withdraw/ — soft-withdraw (idempotent)."""
        from world.stories.services.boundaries import withdraw_treasured_signoff  # noqa: PLC0415

        signoff = self.get_object()
        withdraw_treasured_signoff(signoff)
        signoff.refresh_from_db()
        return Response(self.get_serializer(signoff).data)


# ---------------------------------------------------------------------------
# Custody protection + clearance lifecycle (#2001 Task 6)
# ---------------------------------------------------------------------------


class StoryProtectedSubjectViewSet(viewsets.ModelViewSet):
    """ViewSet for StoryProtectedSubject — GM-authored custody protection (#2001 Task 6).

    Owner-scoped, 404-not-filtered (mirrors ``world.boundaries``'s privacy
    posture): ``get_queryset`` excludes every row belonging to a story the
    requester doesn't own/lead, so a non-owner's GET/PATCH/DELETE against
    another story's protected subject 404s rather than 403ing or leaking the
    GM-only ``notes`` field. ``StoryProtectedSubjectSerializer.validate``
    carries the identical ownership gate for create (DRF never calls
    ``has_object_permission`` for a row that doesn't exist yet).

    ``DELETE`` is overridden to soft-deactivate (``is_active=False``), never
    a hard delete — see ``destroy()`` — mirroring telnet's `story protect
    ... remove`. ``is_active`` also stays writable directly via
    ``PATCH``/``PUT``, so a client may equally reactivate a protection.
    """

    queryset = StoryProtectedSubject.objects.select_related(
        "story",
        "subject_sheet",
        "subject_item",
        "subject_society",
        "subject_organization",
        "beat",
    )
    serializer_class = StoryProtectedSubjectSerializer
    permission_classes = [IsProtectedSubjectStoryOwnerOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = StoryProtectedSubjectFilter
    pagination_class = StandardResultsSetPagination
    ordering_fields = ["created_at"]
    ordering = ["-created_at", "-pk"]

    def get_queryset(self) -> QuerySet[StoryProtectedSubject]:
        """Scope to stories the requester owns/leads (Lead GM); staff sees all."""
        qs = super().get_queryset()
        user = self.request.user
        if not user.is_authenticated:
            return qs.none()
        if user.is_staff:
            return qs
        gm_profile = getattr(user, "gm_profile", None)  # noqa: GETATTR_LITERAL
        filters_q = models.Q(story__owners=user)
        if gm_profile is not None:
            filters_q |= models.Q(story__primary_table__gm=gm_profile)
        return qs.filter(filters_q).distinct()

    @extend_schema(responses={204: None})
    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Soft-deactivate (``is_active=False``), never a hard delete.

        A ``StoryProtectedSubject`` is story-significant data: its
        ``CustodyClearance`` decision trail CASCADEs from it, so a hard
        ``DELETE`` would destroy the record of every grant/deny/escalate/
        resolve/revoke ever made against it (the never-hard-delete-story-
        significant-data rule). Mirrors telnet's `story protect ... remove`
        (``commands/story.py``) exactly — same field, same "204 either way"
        response.
        """
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=["is_active"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class CustodyClearanceViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """ViewSet for CustodyClearance lifecycle (#2001 Task 6).

    No update/destroy — every state transition is a dedicated lifecycle
    action (grant/deny/escalate/resolve/revoke), each mapping 1:1 to
    ``world.stories.services.custody_clearance`` and gated by its own
    permission class per the Task 3 review's binding authority split: staff
    never grants/denies a PENDING request directly, only through
    escalate -> resolve.
    """

    queryset = CustodyClearance.objects.select_related(
        "protected_subject__story__primary_table",
        "requested_by__account",
        "requesting_story",
        "requesting_beat",
        "granted_by__account",
        "staff_resolver",
    )
    serializer_class = CustodyClearanceSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = CustodyClearanceFilter
    ordering_fields = ["created_at"]
    ordering = ["-created_at", "-pk"]

    @property
    def pagination_class(self) -> type[StandardResultsSetPagination] | None:
        """None for create; ``StandardResultsSetPagination`` for list/retrieve.

        ``create``'s response is a bare list (one row per matched protection,
        Task 6 review Fix 4) — never a paginated page. A class-level
        ``pagination_class`` here would make drf-spectacular auto-wrap
        create's ``many=True`` response schema in a ``Paginated...List``
        envelope (its ``_is_list_view``/pagination heuristic keys off
        ``getattr(view, "pagination_class")`` alone, not the action), which
        would not match the actual JSON body create ever returns.
        """
        if self.action == "create":
            return None
        return StandardResultsSetPagination

    def get_permissions(self) -> list[Any]:
        """Create additionally requires GM identity (matching the
        grant/deny/escalate/resolve/revoke actions' own ``IsGMProfile`` gate) — a
        clearance request can only ever be made on behalf of a GMProfile. Every other
        action (list/retrieve, and each lifecycle ``@action``) falls back to
        ``self.permission_classes`` unchanged — the ``@action`` decorator's own
        ``permission_classes`` kwarg already overrides that attribute per-route before
        this runs, so this must not shadow it with a hardcoded default."""
        if self.action == "create":
            return [permissions.IsAuthenticated(), IsGMProfile()]
        return [permission() for permission in self.permission_classes]

    def get_serializer_class(self) -> type[BaseSerializer]:
        """Use the write input serializer for create; the read serializer everywhere else."""
        if self.action == "create":
            return CustodyClearanceRequestSerializer
        return CustodyClearanceSerializer

    def get_queryset(self) -> QuerySet[CustodyClearance]:
        """Requester's own requests + requests targeting stories they own/lead; staff all.

        The ``status=escalated`` filter (see ``CustodyClearanceFilter``) paired
        with the staff-sees-all branch here is the staff escalation-queue read.
        """
        qs = super().get_queryset()
        user = self.request.user
        if not user.is_authenticated:
            return qs.none()
        if user.is_staff:
            return qs
        gm_profile = getattr(user, "gm_profile", None)  # noqa: GETATTR_LITERAL
        filters_q = models.Q(protected_subject__story__owners=user)
        if gm_profile is not None:
            filters_q |= models.Q(requested_by=gm_profile)
            filters_q |= models.Q(protected_subject__story__primary_table__gm=gm_profile)
        return qs.filter(filters_q).distinct()

    @extend_schema(
        request=CustodyClearanceRequestSerializer, responses=CustodyClearanceSerializer(many=True)
    )
    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """POST /api/custody-clearances/ — request_clearance, one row per matched protection.

        Deliberately cross-story: any authenticated GM may request clearance
        for any active protected subject (see
        ``CustodyClearanceRequestSerializer``'s docstring for why the
        ``protected_subject`` queryset is not scoped to the requester's own
        stories). The serializer validates the requester's own GMProfile
        exists and resolves the request to its protection row(s) — either the
        single ``protected_subject`` pk, or (Task 6 review Fix 4) every active
        protection matching an identity group
        (``subject_kind`` + typed pointer/label), for a requester who only
        knows the custodian's username, never the pk.

        A single ``protected_subject`` submission with a live duplicate is a
        hard 400 (unchanged). An identity-path submission matching several
        protections skips any that already have a live request from this
        requester at this scope (the DB partial-unique constraint would
        otherwise raise) and reports those pre-existing rows back alongside
        any newly-created ones — one atomic transaction, one notification per
        newly-created row (``request_clearance`` notifies each row's own
        custodian).
        """
        ser = CustodyClearanceRequestSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        with transaction.atomic():
            created = [
                request_clearance(
                    protected_subject=protection,
                    requested_by=data["requested_by"],
                    scope=data["scope"],
                    requesting_story=data.get("requesting_story"),
                    requesting_beat=data.get("requesting_beat"),
                    message=data.get("message", ""),
                )
                for protection in data["_protections_to_request"]
            ]
        clearances = [*created, *data["_already_pending_clearances"]]
        return Response(
            CustodyClearanceSerializer(clearances, many=True).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        request=CustodyClearanceDecisionInputSerializer, responses=CustodyClearanceSerializer
    )
    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        permission_classes=[IsGMProfile, IsClearanceCustodianGM],
    )
    def grant(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/custody-clearances/{id}/grant/ — custodian GM grants a PENDING request.

        ``IsClearanceCustodianGM`` enforces the exact custodian match with no
        staff bypass — Task 3 review decision: staff act only through
        escalate/resolve, never by posing as the custodian.
        """
        clearance = self.get_object()
        ser = CustodyClearanceDecisionInputSerializer(
            data=request.data, context={"clearance": clearance}
        )
        ser.is_valid(raise_exception=True)
        try:
            updated = grant_clearance(
                clearance,
                granted_by=request.user.gm_profile,
                response_note=ser.validated_data.get("response_note", ""),
            )
        except CustodyClearanceStateError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CustodyClearanceSerializer(updated).data)

    @extend_schema(
        request=CustodyClearanceDecisionInputSerializer, responses=CustodyClearanceSerializer
    )
    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        permission_classes=[IsGMProfile, IsClearanceCustodianGM],
    )
    def deny(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/custody-clearances/{id}/deny/ — custodian GM denies a PENDING request."""
        clearance = self.get_object()
        ser = CustodyClearanceDecisionInputSerializer(
            data=request.data, context={"clearance": clearance}
        )
        ser.is_valid(raise_exception=True)
        try:
            updated = deny_clearance(
                clearance,
                denied_by=request.user.gm_profile,
                response_note=ser.validated_data.get("response_note", ""),
            )
        except CustodyClearanceStateError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CustodyClearanceSerializer(updated).data)

    @extend_schema(request=None, responses=CustodyClearanceSerializer)
    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        permission_classes=[IsGMProfile, IsClearanceRequesterGM],
    )
    def escalate(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/custody-clearances/{id}/escalate/ — requester escalates to staff.

        Only the requesting GM may escalate (``IsClearanceRequesterGM``); the
        service itself takes no actor parameter by design (Task 3 brief).
        """
        clearance = self.get_object()
        ser = CustodyClearanceEscalateInputSerializer(
            data=request.data, context={"clearance": clearance}
        )
        ser.is_valid(raise_exception=True)
        try:
            updated = escalate_clearance(clearance)
        except CustodyClearanceStateError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CustodyClearanceSerializer(updated).data)

    @extend_schema(
        request=CustodyClearanceResolveInputSerializer, responses=CustodyClearanceSerializer
    )
    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        permission_classes=[IsStaffForCustodyResolution],
    )
    def resolve(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/custody-clearances/{id}/resolve/ — staff tiebreak on an ESCALATED request.

        Body: ``{grant: bool, response_note}``. Staff-only
        (``IsStaffForCustodyResolution``) — staff never grant/deny a PENDING
        request directly; this is the only door in.
        """
        clearance = self.get_object()
        ser = CustodyClearanceResolveInputSerializer(
            data=request.data, context={"clearance": clearance}
        )
        ser.is_valid(raise_exception=True)
        try:
            updated = resolve_escalation(
                clearance,
                staff_account=cast(AccountDB, request.user),
                grant=ser.validated_data["grant"],
                response_note=ser.validated_data.get("response_note", ""),
            )
        except (CustodyClearanceStateError, CustodyClearanceAuthorityError) as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CustodyClearanceSerializer(updated).data)

    @extend_schema(request=None, responses=CustodyClearanceSerializer)
    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        permission_classes=[IsClearanceCustodianOrStaff],
    )
    def revoke(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/custody-clearances/{id}/revoke/ — soft-revoke a GRANTED clearance.

        Custodian GM's account, or staff (``IsClearanceCustodianOrStaff`` —
        the one lifecycle action where staff stands in for the custodian
        directly, mirroring ``revoke_clearance``'s own
        ``_is_custodian_account`` check).
        """
        clearance = self.get_object()
        ser = CustodyClearanceRevokeInputSerializer(
            data=request.data, context={"clearance": clearance}
        )
        ser.is_valid(raise_exception=True)
        try:
            revoke_clearance(clearance, revoked_by=cast(AccountDB, request.user))
        except CustodyClearanceStateError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)
        clearance.refresh_from_db()
        return Response(CustodyClearanceSerializer(clearance).data)


class BeatStakeAvailabilityView(APIView):
    """GET /api/beats/{beat_id}/stake-availability/?sheets={id}&sheets={id} (#1771).

    GM-facing counts-only tally of how ``beat``'s candidate stakes screen for
    the given party — reuses ``stake_availability``. Never a reason, never
    which stake or player (ADR-0033): the response is exactly
    ``{available, blocked, needs_signoff}``. Access mirrors ``BeatViewSet``
    (staff or the beat's story owner) since this is a GM planning tool.
    """

    permission_classes = [permissions.IsAuthenticated, IsBeatStoryOwnerOrStaffForAvailability]

    def get(self, request: Request, beat_id: int) -> Response:
        from world.stories.services.boundaries import stake_availability  # noqa: PLC0415

        beat = get_object_or_404(Beat, pk=beat_id)
        self.check_object_permissions(request, beat)

        sheet_ids = request.query_params.getlist("sheets")
        sheets = list(CharacterSheet.objects.filter(pk__in=sheet_ids)) if sheet_ids else []
        availability = stake_availability(beat, sheets)
        return Response(StakeAvailabilitySerializer(availability).data)


class PlayerPendingTreasuredSignoffsView(APIView):
    """GET /api/stories/my-pending-signoffs/?beats=1&beats=2 (#1853).

    Player-safe (never GM-facing): for the requesting player's own account,
    which of the given beats have one of THEIR OWN treasured subjects staked
    without an active sign-off. Batched across beats — the caller passes the
    beat ids it already has on screen (mirrors BeatStakeAvailabilityView's
    multi-value query-param style, but scoped to the caller instead of a
    GM-supplied party).
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses=PendingTreasuredSignoffsSerializer(many=True))
    def get(self, request: Request) -> Response:
        from world.stories.services.boundaries import (  # noqa: PLC0415
            player_pending_treasured_signoffs,
        )

        if not hasattr(request.user, "player_data"):
            return Response([])
        player_data = cast(PlayerData, request.user.player_data)
        beat_ids = [b for b in request.query_params.getlist("beats") if b.isdigit()]
        beats = list(Beat.objects.filter(pk__in=beat_ids))
        entries = player_pending_treasured_signoffs(player_data, beats)
        return Response(PendingTreasuredSignoffsSerializer(entries, many=True).data)
