"""
Character Creation API views.
"""

from django.db import models
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

    Uses the Species model (proxy for Race) from character_sheets.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Return species list filtered by area and heritage."""
        from world.character_sheets.models import Species  # noqa: PLC0415

        heritage_id = request.query_params.get("heritage_id")

        # Get all species allowed in chargen
        queryset = Species.objects.filter(allowed_in_chargen=True)

        if heritage_id:
            # Special heritage = full species list (all allowed species)
            pass  # No additional filtering needed
        else:
            # Normal upbringing = filter to human-only for now
            # TODO: Make this configurable per StartingArea
            queryset = queryset.filter(name__iexact="Human")

        # Serialize using the actual model
        species_data = [
            {"id": s.id, "name": s.name, "description": s.description} for s in queryset
        ]
        serializer = SpeciesSerializer(species_data, many=True)
        return Response(serializer.data)


class FamilyListView(APIView):
    """List families available for a starting area."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Return families filtered by area's realm."""
        area_id = request.query_params.get("area_id")

        queryset = Family.objects.filter(is_playable=True)

        if area_id:
            # Get the realm for this starting area, then filter families
            from world.character_creation.models import StartingArea  # noqa: PLC0415

            area = StartingArea.objects.filter(id=area_id).first()
            if area and area.realm:
                # Include families with no origin_realm or matching realm
                queryset = queryset.filter(
                    models.Q(origin_realm__isnull=True) | models.Q(origin_realm=area.realm)
                )

        serializer = FamilySerializer(queryset, many=True)
        return Response(serializer.data)


class GenderListView(APIView):
    """List available gender options."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Return all gender options."""
        from world.character_creation.serializers import GenderSerializer  # noqa: PLC0415
        from world.character_sheets.models import Gender  # noqa: PLC0415

        queryset = Gender.objects.all()
        serializer = GenderSerializer(queryset, many=True)
        return Response(serializer.data)


class PronounsListView(APIView):
    """List available pronoun sets."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Return all pronoun sets."""
        from world.character_creation.serializers import PronounsSerializer  # noqa: PLC0415
        from world.character_sheets.models import Pronouns  # noqa: PLC0415

        queryset = Pronouns.objects.all()
        serializer = PronounsSerializer(queryset, many=True)
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
