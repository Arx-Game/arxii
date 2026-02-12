"""
Character Creation API views.
"""

from http import HTTPMethod
import logging

from django.db.models import Prefetch
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
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
    MAX_TECHNIQUES_PER_GIFT,
    Beginnings,
    CGPointBudget,
    CharacterDraft,
    DraftAnimaRitual,
    DraftApplication,
    DraftGift,
    DraftMotif,
    DraftMotifResonance,
    DraftMotifResonanceAssociation,
    DraftTechnique,
)
from world.character_creation.serializers import (
    BeginningsSerializer,
    CGPointBudgetSerializer,
    CharacterDraftCreateSerializer,
    CharacterDraftSerializer,
    DraftAnimaRitualSerializer,
    DraftApplicationCommentSerializer,
    DraftApplicationDetailSerializer,
    DraftApplicationSerializer,
    DraftGiftSerializer,
    DraftMotifResonanceAssociationSerializer,
    DraftMotifResonanceSerializer,
    DraftMotifSerializer,
    DraftTechniqueSerializer,
    GenderSerializer,
    PathSerializer,
    PronounsSerializer,
    SpeciesSerializer,
    StartingAreaSerializer,
)
from world.character_creation.services import (
    CharacterCreationError,
    add_application_comment,
    approve_application,
    can_create_character,
    claim_application,
    deny_application,
    ensure_draft_motif,
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
from world.roster.models import Family
from world.roster.serializers import FamilySerializer
from world.species.models import Species
from world.stories.pagination import StandardResultsSetPagination

logger = logging.getLogger(__name__)

NO_ACTIVE_DRAFT_ERROR = "No active draft found"


class StartingAreaViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for listing starting areas."""

    serializer_class = StartingAreaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Return areas filtered by access level."""
        return get_accessible_starting_areas(self.request.user)


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

    def get_queryset(self):
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

    def get_queryset(self):
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

    def get_queryset(self):
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


class CanCreateCharacterView(APIView):
    """Check if current user can create a new character."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Return whether user can create and reason if not."""
        can_create, reason = can_create_character(request.user)
        return Response({"can_create": can_create, "reason": reason})


class CharacterDraftViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing character drafts.

    Each user can have at most one draft. The queryset is filtered
    to only return the current user's draft.
    """

    serializer_class = CharacterDraftSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Return only the current user's drafts."""
        return CharacterDraft.objects.filter(account=self.request.user)

    def get_serializer_class(self):
        """Use different serializer for create action."""
        if self.action == "create":
            return CharacterDraftCreateSerializer
        return CharacterDraftSerializer

    def create(self, request, *args, **kwargs):
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
    def submit(self, request, pk=None):
        """Submit draft for staff review."""
        draft = self.get_object()
        notes = request.data.get("submission_notes", "")

        try:
            application = submit_draft_for_review(draft, submission_notes=notes)
            return Response(
                DraftApplicationSerializer(application).data,
                status=status.HTTP_201_CREATED,
            )
        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=[HTTPMethod.POST], url_path="add-to-roster")
    def add_to_roster(self, request, pk=None):
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
    def cg_points(self, request, pk=None):
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
        cg_data = draft.draft_data.get("cg_points", {})

        return Response(
            {
                "starting_budget": CGPointBudget.get_active_budget(),
                "spent": draft.calculate_cg_points_spent(),
                "remaining": draft.calculate_cg_points_remaining(),
                "breakdown": cg_data.get("breakdown", []),
            }
        )

    @action(detail=True, methods=[HTTPMethod.GET], url_path="projected-resonances")
    def projected_resonances(self, request, pk=None):
        """
        Get projected resonance totals from the draft's selected distinctions.

        Returns a list of resonances the character would have based on
        their distinction selections, without requiring finalization.
        """
        from world.character_creation.serializers import (  # noqa: PLC0415
            ProjectedResonanceSerializer,
        )
        from world.character_creation.services import get_projected_resonances  # noqa: PLC0415

        draft = self.get_object()
        result = get_projected_resonances(draft)
        serializer = ProjectedResonanceSerializer(result, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=[HTTPMethod.POST])
    def unsubmit(self, request, pk=None):
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
        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=[HTTPMethod.POST])
    def resubmit(self, request, pk=None):
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
        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=[HTTPMethod.POST])
    def withdraw(self, request, pk=None):
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
        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(
        detail=True,
        methods=[HTTPMethod.GET],
        url_path="application",
    )
    def get_application(self, request, pk=None):
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
    def add_comment(self, request, pk=None):
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
        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )


class FormOptionsView(APIView):
    """Get form trait options available for a species in character creation."""

    permission_classes = [IsAuthenticated]

    def get(self, request, species_id):
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


class DraftGiftViewSet(viewsets.ModelViewSet):
    """ViewSet for managing draft gifts during character creation."""

    serializer_class = DraftGiftSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return DraftGift.objects.filter(draft__account=self.request.user).prefetch_related(
            "resonances", "techniques__restrictions"
        )

    def perform_create(self, serializer):
        draft = CharacterDraft.objects.filter(account=self.request.user).first()
        if not draft:
            raise ValidationError(NO_ACTIVE_DRAFT_ERROR)
        serializer.save(draft=draft)


class DraftTechniqueViewSet(viewsets.ModelViewSet):
    """ViewSet for managing draft techniques during character creation."""

    serializer_class = DraftTechniqueSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return DraftTechnique.objects.filter(
            gift__draft__account=self.request.user
        ).prefetch_related("restrictions")

    def perform_create(self, serializer):
        gift = serializer.validated_data["gift"]
        if gift.draft.account != self.request.user:
            msg = "Cannot add techniques to another user's gift."
            raise ValidationError(msg)
        if gift.techniques.count() >= MAX_TECHNIQUES_PER_GIFT:
            msg = f"Maximum of {MAX_TECHNIQUES_PER_GIFT} techniques per gift."
            raise ValidationError(msg)
        serializer.save()


class DraftMotifViewSet(viewsets.ModelViewSet):
    """ViewSet for managing draft motif during character creation."""

    serializer_class = DraftMotifSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return DraftMotif.objects.filter(draft__account=self.request.user).prefetch_related(
            "resonances__facet_assignments"
        )

    def perform_create(self, serializer):
        draft = CharacterDraft.objects.filter(account=self.request.user).first()
        if not draft:
            raise ValidationError(NO_ACTIVE_DRAFT_ERROR)
        serializer.save(draft=draft)

    @action(detail=False, methods=[HTTPMethod.POST], url_path="ensure")
    def ensure(self, request):
        """Auto-create/sync motif with resonances from gift and distinctions."""
        draft = CharacterDraft.objects.filter(account=request.user).first()
        if not draft:
            return Response(
                {"detail": NO_ACTIVE_DRAFT_ERROR},
                status=status.HTTP_400_BAD_REQUEST,
            )
        motif = ensure_draft_motif(draft)
        serializer = self.get_serializer(motif)
        return Response(serializer.data)


class DraftMotifResonanceViewSet(viewsets.ModelViewSet):
    """ViewSet for managing draft motif resonances during character creation."""

    serializer_class = DraftMotifResonanceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return DraftMotifResonance.objects.filter(
            motif__draft__account=self.request.user
        ).prefetch_related("associations")


class DraftAnimaRitualViewSet(viewsets.ModelViewSet):
    """ViewSet for managing draft anima ritual during character creation."""

    serializer_class = DraftAnimaRitualSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return DraftAnimaRitual.objects.filter(draft__account=self.request.user)

    def perform_create(self, serializer):
        draft = CharacterDraft.objects.filter(account=self.request.user).first()
        if not draft:
            raise ValidationError(NO_ACTIVE_DRAFT_ERROR)
        serializer.save(draft=draft)


class DraftMotifResonanceAssociationViewSet(viewsets.ModelViewSet):
    """ViewSet for managing facet assignments on draft motif resonances."""

    serializer_class = DraftMotifResonanceAssociationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return DraftMotifResonanceAssociation.objects.filter(
            motif_resonance__motif__draft__account=self.request.user
        ).select_related("facet", "facet__parent", "motif_resonance")


class IsStaffPermission(permissions.BasePermission):
    """Only allow staff users."""

    def has_permission(self, request, view):
        return request.user and request.user.is_staff


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

    def get_serializer_class(self):
        if self.action == "retrieve":
            return DraftApplicationDetailSerializer
        return DraftApplicationSerializer

    def get_queryset(self):
        return (
            DraftApplication.objects.select_related("draft__account", "reviewer")
            .prefetch_related("comments__author")
            .order_by("-submitted_at")
        )

    @action(detail=True, methods=[HTTPMethod.POST])
    def claim(self, request, pk=None):
        """Claim an application for review."""
        application = self.get_object()
        try:
            claim_application(application, reviewer=request.user)
            return Response({"detail": "Application claimed."})
        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=[HTTPMethod.POST])
    def approve(self, request, pk=None):
        """Approve the application."""
        application = self.get_object()
        comment = request.data.get("comment", "")
        try:
            approve_application(application, reviewer=request.user, comment=comment)
            return Response({"detail": "Application approved."})
        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="request-revisions",
    )
    def request_revisions_action(self, request, pk=None):
        """Request revisions on the application."""
        application = self.get_object()
        comment = request.data.get("comment", "")
        try:
            request_revisions(application, reviewer=request.user, comment=comment)
            return Response({"detail": "Revisions requested."})
        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=[HTTPMethod.POST])
    def deny(self, request, pk=None):
        """Deny the application."""
        application = self.get_object()
        comment = request.data.get("comment", "")
        try:
            deny_application(application, reviewer=request.user, comment=comment)
            return Response({"detail": "Application denied."})
        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path="comments",
    )
    def add_staff_comment(self, request, pk=None):
        """Add a comment to the application thread."""
        application = self.get_object()
        text = request.data.get("text", "")
        try:
            comment = add_application_comment(application, author=request.user, text=text)
            return Response(
                DraftApplicationCommentSerializer(comment).data,
                status=status.HTTP_201_CREATED,
            )
        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(
        detail=False,
        methods=[HTTPMethod.GET],
        url_path="pending-count",
    )
    def pending_count(self, request):
        """Get the count of pending applications."""
        count = DraftApplication.objects.filter(status=ApplicationStatus.SUBMITTED).count()
        return Response({"count": count})
