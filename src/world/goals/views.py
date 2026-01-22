"""API views for the goals system."""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from world.goals.models import CharacterGoal, GoalDomain, GoalJournal, GoalRevision
from world.goals.serializers import (
    MAX_GOAL_POINTS,
    CharacterGoalSerializer,
    CharacterGoalUpdateSerializer,
    GoalDomainSerializer,
    GoalJournalCreateSerializer,
    GoalJournalSerializer,
)


class GoalDomainViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for listing goal domains.

    Read-only endpoint for retrieving goal domain definitions.
    """

    queryset = GoalDomain.objects.all()
    serializer_class = GoalDomainSerializer
    permission_classes = [IsAuthenticated]


class CharacterGoalViewSet(viewsets.ViewSet):
    """
    ViewSet for managing a character's goals.

    Provides endpoints for:
    - list: Get character's current goals
    - update_all: Set all goals at once (respecting weekly revision limit)
    - journals: List and create journal entries
    """

    permission_classes = [IsAuthenticated]

    def _get_character(self, request: Request):
        """Get the character for the current user."""
        # Assuming user has a current character - adjust based on actual implementation
        if hasattr(request.user, "character"):
            return request.user.character
        # For roster/puppet systems, might need different logic
        return None

    def list(self, request: Request) -> Response:
        """
        Get character's current goals with summary.

        Returns all goal allocations, total points, and revision status.
        """
        character = self._get_character(request)
        if not character:
            return Response({"detail": "No character found."}, status=status.HTTP_404_NOT_FOUND)

        goals = CharacterGoal.objects.filter(character=character).select_related("domain")
        total_points = sum(g.points for g in goals)

        revision, _ = GoalRevision.objects.get_or_create(character=character)

        data = {
            "goals": CharacterGoalSerializer(goals, many=True).data,
            "total_points": total_points,
            "points_remaining": MAX_GOAL_POINTS - total_points,
            "revision": {
                "last_revised_at": revision.last_revised_at,
                "can_revise": revision.can_revise(),
            },
        }

        return Response(data)

    @action(detail=False, methods=["post"])
    def update_all(self, request: Request) -> Response:
        """
        Update all goals at once.

        Request body:
            {
                "goals": [
                    {"domain_slug": "standing", "points": 15, "notes": "Become Count"},
                    {"domain_slug": "bonds", "points": 10, "notes": "Protect my family"},
                    ...
                ]
            }

        Enforces weekly revision limit unless this is the first time setting goals.
        """
        character = self._get_character(request)
        if not character:
            return Response({"detail": "No character found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = CharacterGoalUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Check revision limit
        revision, _created = GoalRevision.objects.get_or_create(character=character)
        has_existing_goals = CharacterGoal.objects.filter(character=character).exists()

        if has_existing_goals and not revision.can_revise():
            return Response(
                {
                    "detail": "Cannot revise goals yet.",
                    "next_revision_at": revision.last_revised_at,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Clear existing goals and create new ones
        CharacterGoal.objects.filter(character=character).delete()

        for goal_data in serializer.validated_data["goals"]:
            domain = GoalDomain.objects.get(slug=goal_data["domain_slug"])
            if goal_data.get("points", 0) > 0 or goal_data.get("notes"):
                CharacterGoal.objects.create(
                    character=character,
                    domain=domain,
                    points=goal_data.get("points", 0),
                    notes=goal_data.get("notes", ""),
                )

        # Mark as revised
        if has_existing_goals:
            revision.mark_revised()

        # Return updated goals
        goals = CharacterGoal.objects.filter(character=character).select_related("domain")
        total_points = sum(g.points for g in goals)

        return Response(
            {
                "goals": CharacterGoalSerializer(goals, many=True).data,
                "total_points": total_points,
                "points_remaining": MAX_GOAL_POINTS - total_points,
                "revision": {
                    "last_revised_at": revision.last_revised_at,
                    "can_revise": revision.can_revise(),
                },
            }
        )


class GoalJournalViewSet(viewsets.ViewSet):
    """
    ViewSet for managing goal journal entries.

    Provides endpoints for:
    - list: Get character's journal entries
    - create: Create a new journal entry (awards XP)
    - public: Get public journal entries (for roster viewing)
    """

    permission_classes = [IsAuthenticated]

    def _get_character(self, request: Request):
        """Get the character for the current user."""
        if hasattr(request.user, "character"):
            return request.user.character
        return None

    def list(self, request: Request) -> Response:
        """Get character's journal entries."""
        character = self._get_character(request)
        if not character:
            return Response({"detail": "No character found."}, status=status.HTTP_404_NOT_FOUND)

        journals = GoalJournal.objects.filter(character=character).select_related("domain")
        return Response(GoalJournalSerializer(journals, many=True).data)

    def create(self, request: Request) -> Response:
        """
        Create a new journal entry.

        Awards XP for writing about goal progress.

        Request body:
            {
                "domain_slug": "standing" (optional),
                "title": "My journey to power",
                "content": "Today I made progress...",
                "is_public": false
            }
        """
        character = self._get_character(request)
        if not character:
            return Response({"detail": "No character found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = GoalJournalCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        journal = serializer.save(character=character)

        # TODO: Actually award XP to the character
        # character.award_xp(journal.xp_awarded, reason=f"Journal: {journal.title}")

        return Response(GoalJournalSerializer(journal).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def public(self, request: Request) -> Response:
        """
        Get public journal entries.

        Optionally filter by character_id query param for roster viewing.
        """
        character_id = request.query_params.get("character_id")

        queryset = GoalJournal.objects.filter(is_public=True).select_related("domain", "character")

        if character_id:
            queryset = queryset.filter(character_id=character_id)

        # Limit to recent entries
        queryset = queryset[:50]

        return Response(GoalJournalSerializer(queryset, many=True).data)
