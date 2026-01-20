"""
Character Creation API views.
"""

from http import HTTPMethod
import logging

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from world.character_creation.filters import (
    FamilyFilter,
    GenderFilter,
    PathFilter,
    PronounsFilter,
    SpeciesFilter,
)
from world.character_creation.models import (
    Beginnings,
    CGPointBudget,
    CharacterDraft,
)
from world.character_creation.serializers import (
    BeginningsSerializer,
    CGPointBudgetSerializer,
    CharacterDraftCreateSerializer,
    CharacterDraftSerializer,
    GenderSerializer,
    PathSerializer,
    PronounsSerializer,
    SpeciesSerializer,
    StartingAreaSerializer,
)
from world.character_creation.services import (
    CharacterCreationError,
    can_create_character,
    finalize_character,
    get_accessible_starting_areas,
)
from world.character_sheets.models import Gender, Pronouns
from world.classes.models import Path, PathStage
from world.roster.models import Family
from world.roster.serializers import FamilySerializer
from world.species.models import Species

logger = logging.getLogger(__name__)


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

    Only returns active Quiescent-stage paths.
    Uses prefetch_related to avoid N+1 queries when serializing aspects.
    """

    serializer_class = PathSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = PathFilter

    def get_queryset(self):
        """Return only active Quiescent paths for CG."""
        return (
            Path.objects.filter(stage=PathStage.QUIESCENT, is_active=True)
            .prefetch_related("path_aspects__aspect")
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
        """Submit draft for review (player flow)."""
        draft = self.get_object()

        try:
            character = finalize_character(draft, add_to_roster=False)
            return Response(
                {
                    "character_id": character.id,
                    "message": "Character submitted for review.",
                }
            )
        except CharacterCreationError:
            logger.exception("Character creation failed during draft submission.")
            return Response(
                {"detail": "Character creation failed."},
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
