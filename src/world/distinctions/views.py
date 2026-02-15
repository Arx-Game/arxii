"""
API views for the distinctions system.

This module provides ViewSets for:
- DistinctionCategory: Read-only category listings
- Distinction: Read-only distinction listings with filtering
- DraftDistinction: Managing distinctions on a CharacterDraft
"""

from __future__ import annotations

from django.db.models import Prefetch
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from world.character_creation.models import CharacterDraft
from world.character_creation.services import clear_draft_magic_data
from world.distinctions.filters import DistinctionCategoryFilter, DistinctionFilter
from world.distinctions.models import (
    Distinction,
    DistinctionCategory,
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
        """Return active distinctions with prefetched relations, ordered by cost descending."""
        return (
            Distinction.objects.filter(is_active=True)
            .prefetch_related(
                "effects__target__codex_entry",
                "effects__target__category",
                "tags",
                "variants",
                Prefetch(
                    "mutually_exclusive_with",
                    queryset=Distinction.objects.only("id", "name"),
                    to_attr="prefetched_exclusive",
                ),
            )
            .select_related("category")
            .order_by("-cost_per_rank", "name")
        )

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

        # Check variant mutual exclusivity (parent has variants_are_mutually_exclusive=True)
        self._check_variant_exclusions(distinction, existing_ids)

        return ValidatedDistinction(distinction=distinction, rank=rank, notes=notes)

    def _check_mutual_exclusions(self, distinction: Distinction, existing_ids: set[int]) -> None:
        """
        Check for mutual exclusion conflicts.

        Raises:
            ValidationError: If there's a conflict.
        """
        excluded_ids = set(distinction.mutually_exclusive_with.values_list("id", flat=True))
        conflicts = existing_ids & excluded_ids

        if conflicts:
            conflicting = Distinction.objects.filter(id__in=conflicts).first()
            raise ValidationError(
                {
                    "detail": f"Mutually exclusive with {conflicting.name}.",
                    "conflicting_id": conflicting.id,
                }
            )

    def _check_variant_exclusions(self, distinction: Distinction, existing_ids: set[int]) -> None:
        """
        Check for variant mutual exclusivity conflicts.

        If this distinction has a parent with variants_are_mutually_exclusive=True,
        check that no sibling variant is already selected.

        Raises:
            ValidationError: If there's a conflict with a sibling variant.
        """
        parent = distinction.parent_distinction
        if not parent or not parent.variants_are_mutually_exclusive:
            return

        # Get all sibling variant IDs (same parent, excluding self)
        sibling_ids = set(parent.variants.exclude(id=distinction.id).values_list("id", flat=True))
        conflicts = existing_ids & sibling_ids

        if conflicts:
            conflicting = Distinction.objects.filter(id__in=conflicts).first()
            raise ValidationError(
                {
                    "detail": f"Can only select one {parent.name} variant.",
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

        # Clean up any bonus DraftGifts granted by this distinction
        draft.draft_gifts_new.filter(source_distinction_id=pk).delete()

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

        # Clean up any bonus DraftGifts granted by the removed distinction
        draft.draft_gifts_new.filter(source_distinction_id=remove_id).delete()

        return Response({"removed": remove_id, "added": new_entry})

    @action(detail=False, methods=["put"])
    def sync(self, request, draft_id: int):
        """
        Set the full list of distinctions on a draft.

        Request body:
            {
                "distinctions": [{"id": int, "rank": int}, ...]
            }

        This replaces all distinctions on the draft with the provided list.
        All distinctions are validated together for mutual exclusion conflicts.
        """
        draft = self._get_draft(draft_id)

        raw_distinctions = request.data.get("distinctions")
        if raw_distinctions is None:
            raise ValidationError({"detail": "distinctions field is required."})
        if not isinstance(raw_distinctions, list):
            raise ValidationError({"detail": "distinctions must be a list."})

        distinction_entries = []
        for entry in raw_distinctions:
            if not isinstance(entry, dict) or "id" not in entry:
                raise ValidationError({"detail": "Each entry must have an 'id' field."})
            distinction_entries.append({"id": entry["id"], "rank": entry.get("rank", 1)})

        # Handle empty list (clear all distinctions)
        if not distinction_entries:
            self._clear_tradition_if_required_distinction_removed(draft, set())
            draft.draft_data["distinctions"] = []
            draft.save(update_fields=["draft_data", "updated_at"])
            # Clean up all bonus DraftGifts since no distinctions remain
            draft.draft_gifts_new.filter(source_distinction__isnull=False).delete()
            stat_adjustments = draft.enforce_stat_caps()
            return Response({"distinctions": [], "stat_adjustments": stat_adjustments})

        # Build lookup of requested ranks
        requested_ranks = {entry["id"]: entry["rank"] for entry in distinction_entries}
        requested_ids = set(requested_ranks.keys())

        # Fetch all distinctions in one query
        distinctions = (
            Distinction.objects.filter(id__in=requested_ids, is_active=True)
            .select_related("category", "parent_distinction")
            .prefetch_related("mutually_exclusive_with", "parent_distinction__variants")
        )

        found_ids = {d.id for d in distinctions}
        missing_ids = requested_ids - found_ids
        if missing_ids:
            raise ValidationError(
                {"detail": f"Distinctions not found or inactive: {list(missing_ids)}"}
            )

        # Validate ranks
        for distinction in distinctions:
            rank = requested_ranks[distinction.id]
            if not isinstance(rank, int) or rank < 1 or rank > distinction.max_rank:
                raise ValidationError(
                    {
                        "detail": (
                            f"Rank for {distinction.name} must be between 1 and"
                            f" {distinction.max_rank}."
                        )
                    }
                )

        # Validate mutual exclusions
        self._validate_bulk_exclusions(distinctions)

        # Build the new distinctions list
        new_distinctions = []
        for distinction in distinctions:
            rank = requested_ranks[distinction.id]
            entry = self._build_distinction_entry(distinction, rank=rank, notes="")
            new_distinctions.append(entry)

        draft.draft_data["distinctions"] = new_distinctions
        draft.save(update_fields=["draft_data", "updated_at"])

        # Clean up bonus DraftGifts from distinctions no longer in the list
        new_distinction_ids = {d.id for d in distinctions}
        draft.draft_gifts_new.filter(
            source_distinction__isnull=False,
        ).exclude(
            source_distinction_id__in=new_distinction_ids,
        ).delete()

        # Clear tradition if its required distinction was removed
        self._clear_tradition_if_required_distinction_removed(draft, new_distinction_ids)

        stat_adjustments = draft.enforce_stat_caps()

        return Response({"distinctions": new_distinctions, "stat_adjustments": stat_adjustments})

    def _clear_tradition_if_required_distinction_removed(
        self, draft: CharacterDraft, new_distinction_ids: set[int]
    ) -> None:
        """Clear selected tradition if its required distinction was removed.

        Args:
            draft: The character draft being modified.
            new_distinction_ids: Set of distinction IDs in the new selection.
        """
        if not draft.selected_tradition or not draft.selected_beginnings:
            return

        from world.character_creation.models import BeginningTradition  # noqa: PLC0415

        bt = BeginningTradition.objects.filter(
            beginning=draft.selected_beginnings,
            tradition=draft.selected_tradition,
        ).first()
        if (
            bt
            and bt.required_distinction_id
            and bt.required_distinction_id not in new_distinction_ids
        ):
            # Clear all tradition-templated magic data
            clear_draft_magic_data(draft)
            draft.selected_tradition = None
            draft.save(update_fields=["selected_tradition"])

    def _validate_bulk_exclusions(self, distinctions: list[Distinction]) -> None:
        """
        Validate that no mutual exclusions exist between the selected distinctions.

        Raises:
            ValidationError: If any conflicts exist.
        """
        distinction_ids = {d.id for d in distinctions}
        distinctions_by_id = {d.id: d for d in distinctions}

        for distinction in distinctions:
            # Check mutual exclusions
            excluded_ids = set(distinction.mutually_exclusive_with.values_list("id", flat=True))
            conflicts = distinction_ids & excluded_ids
            if conflicts:
                conflicting = distinctions_by_id.get(next(iter(conflicts)))
                msg = f"{distinction.name} is mutually exclusive with {conflicting.name}."
                raise ValidationError(
                    {"detail": msg, "conflicting_ids": [distinction.id, conflicting.id]}
                )

            # Check variant exclusions
            parent = distinction.parent_distinction
            if parent and parent.variants_are_mutually_exclusive:
                sibling_ids = set(
                    parent.variants.exclude(id=distinction.id).values_list("id", flat=True)
                )
                conflicts = distinction_ids & sibling_ids
                if conflicts:
                    conflicting = distinctions_by_id.get(next(iter(conflicts)))
                    raise ValidationError(
                        {
                            "detail": f"Can only select one {parent.name} variant.",
                            "conflicting_ids": [distinction.id, conflicting.id],
                        }
                    )
