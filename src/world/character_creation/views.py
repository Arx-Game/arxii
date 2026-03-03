"""
Character Creation API views.
"""

from http import HTTPMethod
import logging
from typing import Any

from django.db.models import Prefetch, QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer, Serializer
from rest_framework.views import APIView

from world.character_creation.constants import ApplicationStatus
from world.character_creation.filters import (
    FamilyFilter,
    GenderFilter,
    PathFilter,
    PronounsFilter,
    SpeciesFilter,
)
from world.character_creation.models import (
    Beginnings,
    BeginningTradition,
    CGPointBudget,
    CharacterDraft,
    DraftApplication,
)
from world.character_creation.serializers import (
    BeginningsSerializer,
    CGExplanationsSerializer,
    CGPointBudgetSerializer,
    CharacterDraftCreateSerializer,
    CharacterDraftSerializer,
    DraftApplicationCommentSerializer,
    DraftApplicationDetailSerializer,
    DraftApplicationSerializer,
    GenderSerializer,
    PathSerializer,
    PronounsSerializer,
    SpeciesSerializer,
    StartingAreaSerializer,
    TraditionSerializer,
)
from world.character_creation.services import (
    CharacterCreationError,
    add_application_comment,
    approve_application,
    can_create_character,
    claim_application,
    deny_application,
    finalize_character,
    get_accessible_starting_areas,
    request_revisions,
    resubmit_draft,
    submit_draft_for_review,
    unsubmit_draft,
    withdraw_draft,
)
from world.character_sheets.models import Gender, Pronouns
from world.classes.models import Path, PathAspect, PathStage
from world.forms.services import get_cg_form_options
from world.magic.models import Tradition
from world.roster.models import Family
from world.roster.serializers import FamilySerializer
from world.species.models import Species
from world.stories.pagination import StandardResultsSetPagination

logger = logging.getLogger(__name__)


class StartingAreaViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for listing starting areas."""

    serializer_class = StartingAreaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet:
        """Return areas filtered by access level."""
        return get_accessible_starting_areas(self.request.user).select_related("realm")


class BeginningsViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for listing Beginnings options.

    Filter by starting_area to get options available for a specific starting area.
    Results are filtered by user trust level.
    """

    serializer_class = BeginningsSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["starting_area"]

    def get_queryset(self) -> QuerySet[Beginnings]:
        """Return beginnings filtered by availability and access."""
        queryset = (
            Beginnings.objects.filter(is_active=True)
            .select_related("starting_area")
            .prefetch_related("allowed_species", "starting_languages")
        )

        # Filter by trust level
        user = self.request.user
        if not user.is_staff:
            try:
                user_trust = user.trust
                queryset = queryset.filter(trust_required__lte=user_trust)
            except (AttributeError, NotImplementedError):
                # Trust not implemented yet, show all with trust_required=0
                queryset = queryset.filter(trust_required=0)

        return queryset


class SpeciesViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for listing species.

    Returns all species with their parent hierarchy.
    """

    queryset = Species.objects.select_related("parent").prefetch_related("stat_bonuses")
    serializer_class = SpeciesSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = SpeciesFilter


class FamilyViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for listing families.

    Filter by area_id to get families available for a starting area's realm.
    """

    queryset = Family.objects.filter(is_playable=True)
    serializer_class = FamilySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = FamilyFilter


class GenderViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for listing gender options."""

    queryset = Gender.objects.all()
    serializer_class = GenderSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = GenderFilter


class PronounsViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for listing pronoun sets."""

    queryset = Pronouns.objects.all()
    serializer_class = PronounsSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = PronounsFilter


class CGPointBudgetViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for CG point budget configuration.

    Returns the active budget configuration for character creation.
    """

    serializer_class = CGPointBudgetSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[CGPointBudget]:
        """Return only active budgets."""
        return CGPointBudget.objects.filter(is_active=True)


class PathViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for listing paths available in CG.

    Only returns active Prospect-stage paths.
    Uses Prefetch with to_attr to avoid SharedMemoryModel cache pollution.
    """

    serializer_class = PathSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = PathFilter

    def get_queryset(self) -> QuerySet[Path]:
        """Return only active Prospect paths for CG."""
        # Use Prefetch with to_attr targeting the cached_property to avoid
        # polluting SharedMemoryModel's .all() cache. Single cache to invalidate.
        path_aspects_prefetch = Prefetch(
            "path_aspects",
            queryset=PathAspect.objects.select_related("aspect"),
            to_attr="cached_path_aspects",
        )
        return (
            Path.objects.filter(stage=PathStage.PROSPECT, is_active=True)
            .prefetch_related(path_aspects_prefetch)
            .order_by("sort_order", "name")
        )


class TraditionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Lists traditions available for a beginning during CG.

    Query params:
        beginning_id: Filter by beginning (required)
    """

    serializer_class = TraditionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[Tradition]:
        beginning_id = self.request.query_params.get("beginning_id")
        if not beginning_id:
            return Tradition.objects.none()

        from world.codex.models import TraditionCodexGrant  # noqa: PLC0415

        return (
            Tradition.objects.filter(
                beginning_traditions__beginning_id=beginning_id,
                is_active=True,
            )
            .prefetch_related(
                Prefetch(
                    "codex_grants",
                    queryset=TraditionCodexGrant.objects.only("tradition_id", "entry_id"),
                    to_attr="prefetched_codex_grants",
                ),
                Prefetch(
                    "beginning_traditions",
                    queryset=BeginningTradition.objects.filter(
                        beginning_id=beginning_id
                    ).select_related("required_distinction"),
                    to_attr="prefetched_beginning_traditions",
                ),
            )
            .order_by("beginning_traditions__sort_order", "name")
        )

    def get_serializer_context(self) -> dict[str, Any]:
        context = super().get_serializer_context()
        context["beginning_id"] = self.request.query_params.get("beginning_id")
        return context


class CanCreateCharacterView(APIView):
    """Check if current user can create a new character."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        """Return whether user can create and reason if not."""
        can_create, reason = can_create_character(request.user)
        return Response({"can_create": can_create, "reason": reason})


class CGExplanationsView(APIView):
    """Return all CG explanatory text as a flat JSON object."""

    permission_classes = [permissions.AllowAny]

    def get(self, request: Request) -> Response:
        """Return all CG explanation rows as {key: text, ...}."""
        return Response(CGExplanationsSerializer.to_dict())


class CharacterDraftViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing character drafts.

    Each user can have at most one draft. The queryset is filtered
    to only return the current user's draft.
    """

    serializer_class = CharacterDraftSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[CharacterDraft]:
        """Return only the current user's drafts."""
        return CharacterDraft.objects.filter(account=self.request.user).select_related(
            "selected_area__realm",
        )

    def get_serializer_class(self) -> type[Serializer]:
        """Use different serializer for create action."""
        if self.action == "create":
            return CharacterDraftCreateSerializer
        return CharacterDraftSerializer

    def perform_update(self, serializer: BaseSerializer[Any]) -> None:
        """Save the draft."""
        serializer.save()

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Create a new draft, checking eligibility first."""
        # Check if user already has a draft
        if CharacterDraft.objects.filter(account=request.user).exists():
            return Response(
                {"detail": "A draft already exists. Delete it first to start over."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if user can create
        can_create, reason = can_create_character(request.user)
        if not can_create:
            return Response(
                {"detail": reason},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Use parent create, then return full draft data
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        draft = serializer.save()

        # Return full draft data using the detail serializer
        return Response(
            CharacterDraftSerializer(draft, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=[HTTPMethod.POST])
    def submit(self, request: Request, pk: int | None = None) -> Response:
        """Submit draft for staff review."""
        draft = self.get_object()
        notes = request.data.get("submission_notes", "")

        try:
            application = submit_draft_for_review(draft, submission_notes=notes)
            return Response(
                DraftApplicationSerializer(application).data,
                status=status.HTTP_201_CREATED,
            )
        except CharacterCreationError as exc:
            return Response(
                {"detail": exc.reason},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=[HTTPMethod.POST], url_path="add-to-roster")
    def add_to_roster(self, request: Request, pk: int | None = None) -> Response:
        """Add draft directly to roster (staff only)."""
        if not request.user.is_staff:
            return Response(
                {"detail": "Staff permission required."},
                status=status.HTTP_403_FORBIDDEN,
            )

        draft = self.get_object()

        try:
            character = finalize_character(draft, add_to_roster=True)
            return Response(
                {
                    "character_id": character.id,
                    "message": "Character added to roster.",
                }
            )
        except CharacterCreationError:
            logger.exception("Character creation failed while adding to roster.")
            return Response(
                {"detail": "Character creation failed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=[HTTPMethod.GET], url_path="cg-points")
    def cg_points(self, request: Request, pk: int | None = None) -> Response:
        """
        Get detailed CG points breakdown for a draft.

        Returns:
            {
                "starting_budget": 100,
                "spent": 20,
                "remaining": 80,
                "breakdown": [
                    {"category": "heritage", "item": "Elf (Arx)", "cost": 20}
                ]
            }
        """
        draft = self.get_object()

        return Response(
            {
                "starting_budget": CGPointBudget.get_active_budget(),
                "spent": draft.calculate_cg_points_spent(),
                "remaining": draft.calculate_cg_points_remaining(),
                "breakdown": draft.calculate_cg_points_breakdown(),
                "xp_conversion_rate": CGPointBudget.get_active_conversion_rate(),
            }
        )

    @action(detail=True, methods=[HTTPMethod.POST], url_path="select-tradition")
    def select_tradition(self, request: Request, pk: int | None = None) -> Response:
        """Select a tradition for the draft."""
        draft = self.get_object()
        tradition_id = request.data.get("tradition_id")

        if tradition_id is None:
            draft.selected_tradition = None
            draft.save(update_fields=["selected_tradition"])
            return Response({"status": "tradition cleared"})

        if not draft.selected_beginnings:
            raise ValidationError({"detail": "A beginning must be selected first."})

        if not BeginningTradition.objects.filter(
            beginning=draft.selected_beginnings, tradition_id=tradition_id
        ).exists():
            raise ValidationError(
                {"detail": "This tradition is not available for the selected beginning."}
            )

        from django.shortcuts import get_object_or_404  # noqa: PLC0415

        tradition = get_object_or_404(Tradition, pk=tradition_id, is_active=True)
        draft.selected_tradition = tradition
        draft.save(update_fields=["selected_tradition"])

        serializer = self.get_serializer(draft)
        return Response(serializer.data)

    @action(detail=True, methods=[HTTPMethod.POST])
    def unsubmit(self, request: Request, pk: int | None = None) -> Response:
        """Un-submit a draft to resume editing."""
        draft = self.get_object()
        try:
            application = draft.application
        except DraftApplication.DoesNotExist:
            return Response(
                {"detail": "No application found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            unsubmit_draft(application)
            return Response({"detail": "Application un-submitted."})
        except CharacterCreationError as exc:
            return Response(
                {"detail": exc.reason},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=[HTTPMethod.POST])
    def resubmit(self, request: Request, pk: int | None = None) -> Response:
        """Resubmit draft after revisions."""
        draft = self.get_object()
        try:
            application = draft.application
        except DraftApplication.DoesNotExist:
            return Response(
                {"detail": "No application found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        comment = request.data.get("comment", "")
        try:
            resubmit_draft(application, comment=comment)
            return Response({"detail": "Application resubmitted."})
        except CharacterCreationError as exc:
            return Response(
                {"detail": exc.reason},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=[HTTPMethod.POST])
    def withdraw(self, request: Request, pk: int | None = None) -> Response:
        """Withdraw the application."""
        draft = self.get_object()
        try:
            application = draft.application
        except DraftApplication.DoesNotExist:
            return Response(
                {"detail": "No application found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            withdraw_draft(application)
            return Response({"detail": "Application withdrawn."})
        except CharacterCreationError as exc:
            return Response(
                {"detail": exc.reason},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(
        detail=True,
        methods=[HTTPMethod.GET],
        url_path="application",
    )
    def get_application(self, request: Request, pk: int | None = None) -> Response:
        """Get the application for this draft with full thread."""
        draft = self.get_object()
        try:
            application = draft.application
        except DraftApplication.DoesNotExist:
            return Response(
                {"detail": "No application found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = DraftApplicationDetailSerializer(application)
        return Response(serializer.data)

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="application/comments",
    )
    def add_comment(self, request: Request, pk: int | None = None) -> Response:
        """Add a comment to the application thread."""
        draft = self.get_object()
        try:
            application = draft.application
        except DraftApplication.DoesNotExist:
            return Response(
                {"detail": "No application found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        text = request.data.get("text", "")
        try:
            comment = add_application_comment(application, author=request.user, text=text)
            return Response(
                DraftApplicationCommentSerializer(comment).data,
                status=status.HTTP_201_CREATED,
            )
        except CharacterCreationError as exc:
            return Response(
                {"detail": exc.reason},
                status=status.HTTP_400_BAD_REQUEST,
            )


class FormOptionsView(APIView):
    """Get form trait options available for a species in character creation."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, species_id: int) -> Response:
        """Return form traits and options available for the given species."""
        try:
            species = Species.objects.get(id=species_id)
        except Species.DoesNotExist:
            return Response(
                {"detail": "Species not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        form_options = get_cg_form_options(species)

        # Convert dict to list format for serialization
        result = []
        for trait, options in form_options.items():
            result.append(
                {
                    "trait": {
                        "id": trait.id,
                        "name": trait.name,
                        "display_name": trait.display_name,
                        "trait_type": trait.trait_type,
                    },
                    "options": [
                        {
                            "id": opt.id,
                            "name": opt.name,
                            "display_name": opt.display_name,
                            "sort_order": opt.sort_order,
                        }
                        for opt in options
                    ],
                }
            )

        return Response(result)


class IsStaffPermission(permissions.BasePermission):
    """Only allow staff users."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        return bool(request.user and request.user.is_staff)


class DraftApplicationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Staff-only viewset for reviewing draft applications."""

    permission_classes = [IsAuthenticated, IsStaffPermission]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["status"]

    def get_serializer_class(self) -> type[Serializer]:
        if self.action == "retrieve":
            return DraftApplicationDetailSerializer
        return DraftApplicationSerializer

    def get_queryset(self) -> QuerySet[DraftApplication]:
        return (
            DraftApplication.objects.select_related("draft__account", "player_account", "reviewer")
            .prefetch_related("comments__author")
            .order_by("-submitted_at")
        )

    @action(detail=True, methods=[HTTPMethod.POST])
    def claim(self, request: Request, pk: int | None = None) -> Response:
        """Claim an application for review."""
        application = self.get_object()
        try:
            claim_application(application, reviewer=request.user)
            return Response({"detail": "Application claimed."})
        except CharacterCreationError as exc:
            return Response(
                {"detail": exc.reason},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=[HTTPMethod.POST])
    def approve(self, request: Request, pk: int | None = None) -> Response:
        """Approve the application."""
        application = self.get_object()
        comment = request.data.get("comment", "")
        try:
            approve_application(application, reviewer=request.user, comment=comment)
            return Response({"detail": "Application approved."})
        except CharacterCreationError as exc:
            return Response(
                {"detail": exc.reason},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="request-revisions",
    )
    def request_revisions_action(self, request: Request, pk: int | None = None) -> Response:
        """Request revisions on the application."""
        application = self.get_object()
        comment = request.data.get("comment", "")
        try:
            request_revisions(application, reviewer=request.user, comment=comment)
            return Response({"detail": "Revisions requested."})
        except CharacterCreationError as exc:
            return Response(
                {"detail": exc.reason},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=[HTTPMethod.POST])
    def deny(self, request: Request, pk: int | None = None) -> Response:
        """Deny the application."""
        application = self.get_object()
        comment = request.data.get("comment", "")
        try:
            deny_application(application, reviewer=request.user, comment=comment)
            return Response({"detail": "Application denied."})
        except CharacterCreationError as exc:
            return Response(
                {"detail": exc.reason},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="comments",
    )
    def add_staff_comment(self, request: Request, pk: int | None = None) -> Response:
        """Add a comment to the application thread."""
        application = self.get_object()
        text = request.data.get("text", "")
        try:
            comment = add_application_comment(application, author=request.user, text=text)
            return Response(
                DraftApplicationCommentSerializer(comment).data,
                status=status.HTTP_201_CREATED,
            )
        except CharacterCreationError as exc:
            return Response(
                {"detail": exc.reason},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(
        detail=False,
        methods=[HTTPMethod.GET],
        url_path="pending-count",
    )
    def pending_count(self, request: Request) -> Response:
        """Get the count of pending applications."""
        count = DraftApplication.objects.filter(status=ApplicationStatus.SUBMITTED).count()
        return Response({"count": count})
