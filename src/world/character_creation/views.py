"""
Character Creation API views.
"""

from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from world.character_creation.models import CharacterDraft
from world.character_creation.serializers import (
    CharacterDraftCreateSerializer,
    CharacterDraftSerializer,
    FamilySerializer,
    SpeciesSerializer,
    StartingAreaSerializer,
)
from world.character_creation.services import (
    CharacterCreationError,
    can_create_character,
    finalize_character,
    get_accessible_starting_areas,
)
from world.roster.models import Family


class StartingAreaViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for listing starting areas."""

    serializer_class = StartingAreaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Return areas filtered by access level."""
        return get_accessible_starting_areas(self.request.user)


class SpeciesListView(APIView):
    """
    List available species based on area and heritage.

    TODO: Replace with actual Species model when implemented.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Return species list filtered by area and heritage."""
        heritage_id = request.query_params.get("heritage_id")

        # TODO: Implement actual species filtering when Species model exists
        # For now, return stub data
        if heritage_id:
            # Special heritage = full species list
            species = [
                {"id": 1, "name": "Human", "description": "The most common species."},
                {"id": 2, "name": "Elf", "description": "Long-lived and graceful."},
                {"id": 3, "name": "Dwarf", "description": "Stout and resilient."},
                {"id": 4, "name": "Halfling", "description": "Small but spirited."},
            ]
        else:
            # Normal upbringing = humans only for now
            species = [
                {"id": 1, "name": "Human", "description": "The most common species."},
            ]

        serializer = SpeciesSerializer(species, many=True)
        return Response(serializer.data)


class FamilyListView(APIView):
    """List families available for a starting area."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Return families filtered by area."""
        area_id = request.query_params.get("area_id")

        queryset = Family.objects.filter(is_playable=True)

        if area_id:
            # Filter by origin area, or include families with no origin set
            queryset = queryset.filter(origin__isnull=True) | queryset.filter(origin_id=area_id)

        serializer = FamilySerializer(queryset, many=True)
        return Response(serializer.data)


class CanCreateCharacterView(APIView):
    """Check if current user can create a new character."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Return whether user can create and reason if not."""
        can_create, reason = can_create_character(request.user)
        return Response({"can_create": can_create, "reason": reason})


class CharacterDraftView(APIView):
    """
    Manage the current user's character draft.

    GET: Retrieve current draft
    POST: Create new draft
    PATCH: Update draft
    DELETE: Delete draft
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get the user's current draft."""
        draft = CharacterDraft.objects.filter(account=request.user).first()
        if not draft:
            return Response(
                {"detail": "No draft found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = CharacterDraftSerializer(draft, context={"request": request})
        return Response(serializer.data)

    def post(self, request):
        """Create a new draft."""
        # Check if user already has a draft
        existing = CharacterDraft.objects.filter(account=request.user).first()
        if existing:
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

        serializer = CharacterDraftCreateSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        draft = serializer.save()

        # Return full draft data
        return Response(
            CharacterDraftSerializer(draft, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    def patch(self, request):
        """Update the current draft."""
        draft = CharacterDraft.objects.filter(account=request.user).first()
        if not draft:
            return Response(
                {"detail": "No draft found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = CharacterDraftSerializer(
            draft,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request):
        """Delete the current draft."""
        draft = CharacterDraft.objects.filter(account=request.user).first()
        if draft:
            draft.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SubmitDraftView(APIView):
    """Submit draft for review (player flow)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Finalize draft and submit for approval."""
        draft = CharacterDraft.objects.filter(account=request.user).first()
        if not draft:
            return Response(
                {"detail": "No draft found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            character = finalize_character(draft, add_to_roster=False)
            return Response(
                {
                    "character_id": character.id,
                    "message": "Character submitted for review.",
                }
            )
        except CharacterCreationError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )


class AddToRosterView(APIView):
    """Add draft directly to roster (staff/GM flow)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Finalize draft and add to roster (staff only)."""
        if not request.user.is_staff:
            return Response(
                {"detail": "Staff permission required."},
                status=status.HTTP_403_FORBIDDEN,
            )

        draft = CharacterDraft.objects.filter(account=request.user).first()
        if not draft:
            return Response(
                {"detail": "No draft found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            character = finalize_character(draft, add_to_roster=True)
            return Response(
                {
                    "character_id": character.id,
                    "message": "Character added to roster.",
                }
            )
        except CharacterCreationError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
