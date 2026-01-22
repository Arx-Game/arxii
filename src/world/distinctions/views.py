"""
API views for the distinctions system.

This module provides ViewSets for:
- DistinctionCategory: Read-only category listings
- Distinction: Read-only distinction listings with filtering
- DraftDistinction: Managing distinctions on a CharacterDraft
"""

from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from world.character_creation.models import CharacterDraft
from world.distinctions.filters import DistinctionCategoryFilter, DistinctionFilter
from world.distinctions.models import (
    Distinction,
    DistinctionCategory,
    DistinctionMutualExclusion,
)
from world.distinctions.serializers import (
    DistinctionCategorySerializer,
    DistinctionDetailSerializer,
    DistinctionListSerializer,
)
from world.distinctions.types import DraftDistinctionEntry, ValidatedDistinction


class DistinctionCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for listing distinction categories.

    Read-only endpoint for retrieving distinction categories.
    """

    queryset = DistinctionCategory.objects.all()
    serializer_class = DistinctionCategorySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = DistinctionCategoryFilter


class DistinctionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for listing distinctions.

    Supports filtering by:
    - category: Filter by category slug
    - search: Search name, description, tags, and effect descriptions
    - exclude_variants: Exclude variant distinctions (show only parents/standalone)
    - draft_id: Add lock status based on draft's existing distinctions
    """

    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = DistinctionFilter

    def get_queryset(self):
        """Return active distinctions with prefetched relations."""
        queryset = Distinction.objects.filter(is_active=True).prefetch_related(
            "effects", "tags", "variants"
        )

        # Handle exclude_variants parameter
        exclude_variants = self.request.query_params.get("exclude_variants")
        if exclude_variants and exclude_variants.lower() == "true":
            queryset = queryset.filter(parent_distinction__isnull=True)

        # Handle search parameter
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(description__icontains=search)
                | Q(tags__name__icontains=search)
                | Q(effects__description__icontains=search)
            ).distinct()

        return queryset.select_related("category")

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == "retrieve":
            return DistinctionDetailSerializer
        return DistinctionListSerializer

    def get_serializer_context(self):
        """Add draft context for lock status calculation."""
        context = super().get_serializer_context()

        draft_id = self.request.query_params.get("draft_id")
        if draft_id:
            try:
                draft = CharacterDraft.objects.get(id=draft_id, account=self.request.user)
                context["draft"] = draft
            except CharacterDraft.DoesNotExist:
                pass

        return context


class DraftDistinctionViewSet(viewsets.ViewSet):
    """
    ViewSet for managing distinctions on a CharacterDraft.

    Provides endpoints for:
    - list: Get draft's current distinctions
    - create: Add a distinction to the draft
    - destroy: Remove a distinction from the draft
    - swap: Swap mutually exclusive distinctions
    """

    permission_classes = [IsAuthenticated]

    def _get_draft(self, draft_id: int) -> CharacterDraft:
        """
        Get CharacterDraft by ID and verify ownership.

        Raises:
            NotFound: If draft not found or not owned by user.
        """
        try:
            return CharacterDraft.objects.get(id=draft_id, account=self.request.user)
        except CharacterDraft.DoesNotExist:
            msg = "Draft not found."
            raise NotFound(msg) from None

    def _validate_distinction_for_add(
        self, data: dict, existing_ids: set[int]
    ) -> ValidatedDistinction:
        """
        Validate distinction data for adding to a draft.

        Args:
            data: Request data with distinction_id, rank, notes.
            existing_ids: Set of distinction IDs already on the draft.

        Returns:
            ValidatedDistinction with the validated data.

        Raises:
            ValidationError: If validation fails.
            NotFound: If distinction not found.
        """
        distinction_id = data.get("distinction_id")
        rank = data.get("rank", 1)
        notes = data.get("notes", "")

        if not distinction_id:
            raise ValidationError({"detail": "distinction_id is required."})

        # Get distinction
        try:
            distinction = Distinction.objects.get(id=distinction_id, is_active=True)
        except Distinction.DoesNotExist:
            msg = "Distinction not found or inactive."
            raise NotFound(msg) from None

        # Validate rank
        if not isinstance(rank, int) or rank < 1 or rank > distinction.max_rank:
            raise ValidationError({"detail": f"Rank must be between 1 and {distinction.max_rank}."})

        # Check if already on draft
        if distinction_id in existing_ids:
            raise ValidationError({"detail": "Distinction already on draft."})

        # Check mutual exclusions
        self._check_mutual_exclusions(distinction, existing_ids)

        return ValidatedDistinction(distinction=distinction, rank=rank, notes=notes)

    def _check_mutual_exclusions(self, distinction: Distinction, existing_ids: set[int]) -> None:
        """
        Check for mutual exclusion conflicts.

        Raises:
            ValidationError: If there's a conflict.
        """
        excluded = DistinctionMutualExclusion.get_excluded_for(distinction)
        excluded_ids = {d.id for d in excluded}
        conflicts = existing_ids & excluded_ids

        if conflicts:
            conflicting = Distinction.objects.filter(id__in=conflicts).first()
            raise ValidationError(
                {
                    "detail": f"Mutually exclusive with {conflicting.name}.",
                    "conflicting_id": conflicting.id,
                }
            )

    def _build_distinction_entry(
        self, distinction: Distinction, rank: int, notes: str
    ) -> DraftDistinctionEntry:
        """Build the dictionary entry for a distinction on a draft."""
        return DraftDistinctionEntry(
            distinction_id=distinction.id,
            distinction_name=distinction.name,
            distinction_slug=distinction.slug,
            category_slug=distinction.category.slug,
            rank=rank,
            cost=distinction.calculate_total_cost(rank),
            notes=notes,
        )

    def list(self, request, draft_id: int):
        """
        List distinctions currently on the draft.

        Returns the distinctions array from draft.draft_data.
        """
        draft = self._get_draft(draft_id)
        distinctions = draft.draft_data.get("distinctions", [])
        return Response(distinctions)

    def create(self, request, draft_id: int):
        """
        Add a distinction to the draft.

        Request body:
            {
                "distinction_id": int,
                "rank": int (optional, defaults to 1),
                "notes": str (optional)
            }
        """
        draft = self._get_draft(draft_id)
        distinctions = draft.draft_data.get("distinctions", [])
        existing_ids = {d.get("distinction_id") for d in distinctions}

        validated = self._validate_distinction_for_add(request.data, existing_ids)

        new_entry = self._build_distinction_entry(
            validated.distinction, validated.rank, validated.notes
        )
        distinctions.append(new_entry)

        draft.draft_data["distinctions"] = distinctions
        draft.save(update_fields=["draft_data", "updated_at"])

        return Response(new_entry, status=status.HTTP_201_CREATED)

    def destroy(self, request, draft_id: int, pk: int):
        """
        Remove a distinction from the draft.

        Args:
            draft_id: The draft to modify.
            pk: The distinction_id to remove.
        """
        draft = self._get_draft(draft_id)
        distinctions = draft.draft_data.get("distinctions", [])
        original_count = len(distinctions)

        distinctions = [d for d in distinctions if d.get("distinction_id") != pk]

        if len(distinctions) == original_count:
            msg = "Distinction not found on draft."
            raise NotFound(msg)

        draft.draft_data["distinctions"] = distinctions
        draft.save(update_fields=["draft_data", "updated_at"])

        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["post"])
    def swap(self, request, draft_id: int):
        """
        Swap mutually exclusive distinctions.

        Request body:
            {
                "remove_id": int,
                "add_id": int,
                "rank": int (optional, defaults to 1),
                "notes": str (optional)
            }

        This atomically removes one distinction and adds another,
        useful for swapping between mutually exclusive options.
        """
        draft = self._get_draft(draft_id)

        remove_id = request.data.get("remove_id")
        add_id = request.data.get("add_id")

        if not remove_id or not add_id:
            raise ValidationError({"detail": "Both remove_id and add_id are required."})

        # Remove the old distinction first
        distinctions = draft.draft_data.get("distinctions", [])
        new_distinctions = []
        found = False

        for d in distinctions:
            if d.get("distinction_id") == remove_id:
                found = True
            else:
                new_distinctions.append(d)

        if not found:
            msg = "Distinction to remove not found on draft."
            raise NotFound(msg)

        # Now validate and add the new distinction
        existing_ids = {d.get("distinction_id") for d in new_distinctions}
        add_data = {
            "distinction_id": add_id,
            "rank": request.data.get("rank", 1),
            "notes": request.data.get("notes", ""),
        }
        validated = self._validate_distinction_for_add(add_data, existing_ids)

        new_entry = self._build_distinction_entry(
            validated.distinction, validated.rank, validated.notes
        )
        new_distinctions.append(new_entry)

        draft.draft_data["distinctions"] = new_distinctions
        draft.save(update_fields=["draft_data", "updated_at"])

        return Response({"removed": remove_id, "added": new_entry})
