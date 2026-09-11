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
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from world.character_creation.constants import OfferArrival
from world.character_creation.models import CharacterDraft, DistinctionOffer
from world.character_creation.offers import opener_label, reconcile_offer_picks, visible_offers
from world.codex.models import DistinctionCodexGrant
from world.distinctions.filters import DistinctionCategoryFilter, DistinctionFilter
from world.distinctions.models import (
    Distinction,
    DistinctionCategory,
    DistinctionEffect,
    DistinctionTag,
)
from world.distinctions.serializers import (
    DistinctionCategorySerializer,
    DistinctionDetailSerializer,
    DistinctionListSerializer,
    DraftDistinctionCreateSerializer,
    DraftDistinctionEntrySerializer,
    DraftDistinctionSwapSerializer,
    DraftDistinctionSyncSerializer,
)
from world.distinctions.types import ValidatedDistinction, build_distinction_entry


class DistinctionCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for listing distinction categories.

    Read-only endpoint for retrieving distinction categories.
    """

    pagination_class = None  # 2026-07 audit: opt out of default paginator (ADR-0138)

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

    pagination_class = None  # 2026-07 audit: opt out of default paginator (ADR-0138)

    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = DistinctionFilter

    def get_queryset(self):
        """Return active distinctions with prefetched relations, ordered by cost descending."""
        return (
            Distinction.objects.filter(is_active=True)
            .prefetch_related(
                Prefetch(
                    "effects",
                    queryset=DistinctionEffect.objects.select_related("target__category"),
                    to_attr="cached_effects",
                ),
                Prefetch(
                    "tags",
                    queryset=DistinctionTag.objects.all(),
                    to_attr="cached_tags",
                ),
                Prefetch(
                    "variants",
                    queryset=Distinction.objects.filter(is_active=True),
                    to_attr="cached_variants",
                ),
                Prefetch(
                    "mutually_exclusive_with",
                    queryset=Distinction.objects.all(),
                    to_attr="prefetched_exclusive",
                ),
                Prefetch(
                    "codex_grants",
                    queryset=DistinctionCodexGrant.objects.all(),
                    to_attr="cached_codex_grants",
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

        filterset = DistinctionFilter(
            self.request.query_params, queryset=Distinction.objects.none()
        )
        if filterset.form.is_valid():
            draft_id = filterset.form.cleaned_data.get("draft_id")
            if draft_id:
                try:
                    draft = CharacterDraft.objects.get(id=int(draft_id), account=self.request.user)
                    context["draft"] = draft
                except CharacterDraft.DoesNotExist:
                    pass

        return context


@extend_schema(tags=["distinctions"])
class DraftDistinctionViewSet(viewsets.ViewSet):
    """
    ViewSet for managing distinctions on a CharacterDraft.

    Provides endpoints for:
    - list: Get draft's current distinctions
    - create: Add a distinction to the draft
    - destroy: Remove a distinction from the draft
    - swap: Swap mutually exclusive distinctions
    """

    # Schema default read shape — drf-spectacular uses this for
    # introspection on viewsets.ViewSet; per-action decorators override.
    serializer_class = DraftDistinctionEntrySerializer
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
        self, data: dict, existing_ids: set[int], draft: CharacterDraft
    ) -> ValidatedDistinction:
        """
        Validate distinction data for adding to a draft.

        Args:
            data: Request data with distinction_id, rank, notes, offer_id.
            existing_ids: Set of distinction IDs already on the draft.
            draft: The draft being edited (species-innate gate, #2846).

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

        # Per-feature picks come only through ``sync`` (#3739), which is the one path
        # that carries the feature. Adding one here would store an entry with no
        # feature at all, which no later reader could place on a trait or a marking.
        if distinction.taken_per_feature:
            raise ValidationError(
                {"detail": f"{distinction.name} is taken on a feature, in the Appearance stage."}
            )

        # Validate rank
        ceiling = distinction.cg_ceiling
        if not isinstance(rank, int) or rank < 1 or rank > ceiling:
            raise ValidationError({"detail": f"Rank must be between 1 and {ceiling}."})

        # Check if already on draft
        if distinction_id in existing_ids:
            raise ValidationError({"detail": "Distinction already on draft."})

        # Check mutual exclusions
        self._check_mutual_exclusions(distinction, existing_ids)

        # Check variant mutual exclusivity (parent has variants_are_mutually_exclusive=True)
        self._check_variant_exclusions(distinction, existing_ids)

        # Species-innate gate (#2846)
        self._check_species_innate(distinction, draft)

        # Offer gate (#3675): every CG pick must resolve to an offer the draft earned.
        offer = self._resolve_offer(data.get("offer_id"), distinction, draft)

        return ValidatedDistinction(distinction=distinction, rank=rank, notes=notes, offer=offer)

    def _resolve_offer(
        self, offer_id: object, distinction: Distinction, draft: CharacterDraft
    ) -> DistinctionOffer:
        """Resolve and validate an ``offer_id`` against the draft's visible offers.

        Called by ``_validate_distinction_for_add`` and ``sync``. Raises when the
        id isn't an int (carried sources are string keys a client never sends),
        when the offer isn't visible to this draft or names a different
        distinction, or when the offer doesn't arrive as a CHOICE (a client may
        never pick a BUNDLED or CARRIED offer directly, those are applied only
        by ``reconcile_offer_picks``).
        """
        if not isinstance(offer_id, int):
            raise ValidationError({"detail": f"{distinction.name} requires an offer_id."})
        visible = visible_offers(draft)
        offer = visible.get(offer_id)
        if (
            offer is None
            or offer.distinction_id != distinction.id
            or offer.arrives_as != OfferArrival.CHOICE
        ):
            hidden = (
                DistinctionOffer.objects.filter(pk=offer_id)
                .select_related("glimpse_tag", "origin_choice", "schooling_line")
                .first()
            )
            label = opener_label(hidden) if hidden else "this chapter"
            raise ValidationError(
                {"detail": f"{distinction.name} is not offered to you here ({label})."}
            )
        return offer

    def _check_species_innate_bulk(self, distinctions, draft: CharacterDraft) -> None:
        """Apply the species-innate gate (#2846) to every distinction in a sync payload."""
        for distinction in distinctions:
            self._check_species_innate(distinction, draft)

    def _check_species_innate(self, distinction: Distinction, draft: CharacterDraft) -> None:
        """Reject selecting a distinction the drafted species grants innately (#2846).

        The species' own ``SpeciesGiftGrant.drawback_distinction`` rows stamp at
        finalize — selecting one in CG would double it up (and, for the
        reimbursing sun drawbacks, double-refund the counterweight).
        """
        if draft.selected_species_id is None:
            return
        from world.species.services import species_innate_distinction_ids  # noqa: PLC0415

        if distinction.id in species_innate_distinction_ids(draft.selected_species):
            raise ValidationError(
                {
                    "detail": (
                        f"{distinction.name} is innate to your selected species "
                        "and cannot be taken as a choice."
                    ),
                }
            )

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
        self,
        distinction: Distinction,
        rank: int,
        notes: str,
        offer: DistinctionOffer,
        draft: CharacterDraft,
    ):
        """Build the dictionary entry for a distinction on a draft, from its offer."""
        return build_distinction_entry(
            distinction, rank, notes, offer=offer, source=opener_label(offer, draft=draft)
        )

    @extend_schema(responses=DraftDistinctionEntrySerializer(many=True))
    def list(self, request, draft_id: int):
        """
        List distinctions currently on the draft.

        Returns the distinctions array from draft.draft_data.
        """
        draft = self._get_draft(draft_id)
        distinctions = draft.draft_data.get("distinctions", [])
        return Response(distinctions)

    @extend_schema(
        request=DraftDistinctionCreateSerializer,
        responses=DraftDistinctionEntrySerializer,
    )
    def create(self, request, draft_id: int):
        """
        Add a distinction to the draft.

        Request body:
            {
                "distinction_id": int,
                "offer_id": int,
                "rank": int (optional, defaults to 1),
                "notes": str (optional)
            }
        """
        draft = self._get_draft(draft_id)
        distinctions = draft.draft_data.get("distinctions", [])
        existing_ids = {d.get("distinction_id") for d in distinctions}

        validated = self._validate_distinction_for_add(request.data, existing_ids, draft)

        new_entry = self._build_distinction_entry(
            validated.distinction, validated.rank, validated.notes, validated.offer, draft
        )
        distinctions.append(new_entry)

        draft.draft_data["distinctions"] = distinctions
        draft.save(update_fields=["draft_data", "updated_at"])

        return Response(new_entry, status=status.HTTP_201_CREATED)

    @extend_schema(responses={204: None})
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
        reconcile_offer_picks(draft)

        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        request=DraftDistinctionSwapSerializer,
        responses=inline_serializer(
            name="DraftDistinctionSwapResult",
            fields={
                "removed": serializers.IntegerField(),
                "added": DraftDistinctionEntrySerializer(),
            },
        ),
    )
    @action(detail=False, methods=["post"])
    def swap(self, request, draft_id: int):
        """
        Swap mutually exclusive distinctions.

        Request body:
            {
                "remove_id": int,
                "add_id": int,
                "offer_id": int,
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
            "offer_id": request.data.get("offer_id"),
        }
        validated = self._validate_distinction_for_add(add_data, existing_ids, draft)

        new_entry = self._build_distinction_entry(
            validated.distinction, validated.rank, validated.notes, validated.offer, draft
        )
        new_distinctions.append(new_entry)

        draft.draft_data["distinctions"] = new_distinctions
        draft.save(update_fields=["draft_data", "updated_at"])
        reconcile_offer_picks(draft)

        return Response({"removed": remove_id, "added": new_entry})

    @extend_schema(
        request=DraftDistinctionSyncSerializer,
        responses=inline_serializer(
            name="DraftDistinctionSyncResult",
            fields={"distinctions": DraftDistinctionEntrySerializer(many=True)},
        ),
    )
    @action(detail=False, methods=["put"])
    def sync(self, request, draft_id: int):
        """
        Set the full list of CHOICE distinctions on a draft, then reconcile (#3675).

        Request body:
            {
                "distinctions": [{"id": int, "rank": int, "offer_id": int}, ...]
            }

        This replaces every CHOICE-arrival distinction on the draft with the
        provided list; every entry must resolve to an offer the draft earned
        (``_resolve_offer``). ``reconcile_offer_picks`` runs afterward so any
        BUNDLED/CARRIED entries the frontend never sends survive the sync.
        """
        draft = self._get_draft(draft_id)
        distinction_entries = self._parse_sync_payload(request.data.get("distinctions"))

        # Handle empty list (clear all CHOICE distinctions)
        if not distinction_entries:
            draft.draft_data["distinctions"] = []
            draft.save(update_fields=["draft_data", "updated_at"])
            reconcile_offer_picks(draft)
            return Response({"distinctions": draft.draft_data.get("distinctions", [])})

        by_id = self._fetch_sync_distinctions(distinction_entries)
        self._validate_sync_ranks(distinction_entries, by_id)

        # Validate mutual exclusions
        self._validate_bulk_exclusions(list(by_id.values()))

        # Species-innate gate (#2846)
        self._check_species_innate_bulk(list(by_id.values()), draft)

        new_distinctions = self._build_sync_entries(distinction_entries, by_id, draft)

        draft.draft_data["distinctions"] = new_distinctions
        draft.save(update_fields=["draft_data", "updated_at"])
        reconcile_offer_picks(draft)

        return Response({"distinctions": draft.draft_data.get("distinctions", [])})

    def _parse_sync_payload(self, raw_distinctions: object) -> list[dict]:
        """Validate the sync request shape and normalize each entry.

        Called by ``sync``. Raises on a missing/malformed ``distinctions`` field
        or an entry missing its ``id``.
        """
        if raw_distinctions is None:
            raise ValidationError({"detail": "distinctions field is required."})
        if not isinstance(raw_distinctions, list):
            raise ValidationError({"detail": "distinctions must be a list."})

        entries = []
        for entry in raw_distinctions:
            id_key = "id"
            if not isinstance(entry, dict) or id_key not in entry:
                raise ValidationError({"detail": "Each entry must have an 'id' field."})
            entries.append(
                {
                    "id": entry["id"],
                    "rank": entry.get("rank", 1),
                    "offer_id": entry.get("offer_id"),
                    # #3739: which feature this pick is aimed at, for the per-feature
                    # distinctions. A trait row is named by ``FormTrait.name`` and a
                    # marking by its ``DraftMarking`` pk; at most one is ever sent.
                    "feature_trait": entry.get("feature_trait") or "",
                    "feature_marking": entry.get("feature_marking") or 0,
                }
            )
        return entries

    def _fetch_sync_distinctions(self, distinction_entries: list[dict]) -> dict[int, Distinction]:
        """Fetch every requested distinction in one query, prefetched for exclusion checks.

        Called by ``sync``. Raises when an id is missing or inactive.
        """
        requested_ids = {entry["id"] for entry in distinction_entries}
        distinctions = (
            Distinction.objects.filter(id__in=requested_ids, is_active=True)
            .select_related("category", "parent_distinction")
            .prefetch_related(
                Prefetch(
                    "mutually_exclusive_with",
                    queryset=Distinction.objects.all(),
                    to_attr="cached_mutually_exclusive_with",
                ),
                Prefetch(
                    "parent_distinction__variants",
                    queryset=Distinction.objects.all(),
                    to_attr="cached_variants",
                ),
            )
        )
        by_id = {d.id: d for d in distinctions}
        missing_ids = requested_ids - set(by_id)
        if missing_ids:
            raise ValidationError(
                {"detail": f"Distinctions not found or inactive: {list(missing_ids)}"}
            )
        return by_id

    def _validate_sync_ranks(
        self, distinction_entries: list[dict], by_id: dict[int, Distinction]
    ) -> None:
        """Raise if any entry's rank is out of bounds for its distinction.

        Called by ``sync``. The ceiling is ``Distinction.cg_ceiling`` (#3739), which
        is ``max_rank`` for everything that has not set a lower character-creation
        cap; the presence axes reach 5 in play and stop at 3 here.
        """
        for entry in distinction_entries:
            distinction = by_id[entry["id"]]
            rank = entry["rank"]
            ceiling = distinction.cg_ceiling
            if not isinstance(rank, int) or rank < 1 or rank > ceiling:
                raise ValidationError(
                    {"detail": f"Rank for {distinction.name} must be between 1 and {ceiling}."}
                )

    def _build_sync_entries(
        self,
        distinction_entries: list[dict],
        by_id: dict[int, Distinction],
        draft: CharacterDraft,
    ) -> list[dict]:
        """Resolve each entry's offer and build the merged draft-entry list.

        Called by ``sync``. An entry for a distinction already added from
        another offer in this same payload merges into it (offer_ids/sources/
        arrivals appended, rank raised to the max requested).
        """
        labels = self._resolve_sync_features(distinction_entries, by_id, draft)
        new_by_key: dict[tuple[int, str, int], dict] = {}
        for entry in distinction_entries:
            distinction = by_id[entry["id"]]
            rank = entry["rank"]
            offer = self._resolve_offer(entry["offer_id"], distinction, draft)
            trait_name, marking_id = self._entry_feature(entry, distinction)
            key = (distinction.id, trait_name, marking_id)
            # A per-feature line names the same offer on every feature, so its source
            # is the feature's own display name (#3739) -- "Hair Color", "a burn scar"
            # -- which is what ``CharacterDistinction.source_description`` should read.
            source = labels.get(key[1:]) or opener_label(offer, draft=draft)
            existing = new_by_key.get(key)
            if existing is None:
                new_by_key[key] = build_distinction_entry(
                    distinction,
                    rank,
                    "",
                    offer=offer,
                    source=source,
                    feature_trait=trait_name,
                    feature_marking=marking_id,
                )
                continue
            existing["rank"] = max(existing["rank"], rank)
            existing["cost"] = distinction.calculate_total_cost(existing["rank"])
            if offer.id not in existing["offer_ids"]:
                existing["offer_ids"].append(offer.id)
                existing["sources"].append(source)
                existing["arrivals"].append(offer.arrives_as)
        return list(new_by_key.values())

    @staticmethod
    def _entry_feature(entry: dict, distinction: Distinction) -> tuple[str, int]:
        """The feature one sync entry names, as ``(trait name, draft marking id)``.

        Called by ``_build_sync_entries``. A distinction that is not
        ``taken_per_feature`` never carries a feature, so anything the client sent
        on it is dropped rather than stored -- ``_resolve_sync_features`` has
        already rejected the payload if it named one.
        """
        if not distinction.taken_per_feature:
            return "", 0
        return entry["feature_trait"], entry["feature_marking"]

    def _resolve_sync_features(
        self,
        distinction_entries: list[dict],
        by_id: dict[int, Distinction],
        draft: CharacterDraft,
    ) -> dict[tuple[str, int], str]:
        """Validate every entry's feature and return each one's display label (#3739).

        Called by ``_build_sync_entries``. Four things are checked, because a
        per-feature pick is priced per feature and the feature is the only thing
        that keeps two picks of one distinction apart:

        * a ``taken_per_feature`` distinction names exactly one feature;
        * anything else names none;
        * a named trait is a real ``FormTrait`` and a named marking is one of *this*
          draft's own ``DraftMarking`` rows (never another player's);
        * a ``requires_feature_opened`` axis is bought on a feature this same payload
          also unlocks -- the sync is the whole truth about the draft's CHOICE picks,
          so the unlock has to be in it.

        The returned mapping is keyed by ``(trait name, draft marking id)`` and holds
        the feature's own display name, which becomes the entry's source.
        """
        from world.forms.models import FormTrait  # noqa: PLC0415

        named: set[tuple[str, int]] = set()
        for entry in distinction_entries:
            distinction = by_id[entry["id"]]
            trait_name, marking_id = entry["feature_trait"], entry["feature_marking"]
            if not distinction.taken_per_feature:
                if trait_name or marking_id:
                    raise ValidationError(
                        {"detail": f"{distinction.name} is not taken on a single feature."}
                    )
                continue
            if bool(trait_name) == bool(marking_id):
                raise ValidationError(
                    {"detail": f"{distinction.name} must name exactly one feature."}
                )
            named.add((trait_name, marking_id))

        if not named:
            return {}

        traits = {
            t.name: t.display_name
            for t in FormTrait.objects.filter(name__in={n for n, _ in named if n})
        }
        markings = {
            m.pk: (m.name or m.get_kind_display())
            for m in draft.markings.filter(pk__in={m for _, m in named if m})
        }
        labels: dict[tuple[str, int], str] = {}
        for trait_name, marking_id in named:
            if trait_name and trait_name not in traits:
                raise ValidationError({"detail": f"No such feature: {trait_name}."})
            if marking_id and marking_id not in markings:
                raise ValidationError({"detail": "That marking is not on this draft."})
            labels[(trait_name, marking_id)] = (
                traits[trait_name] if trait_name else markings[marking_id]
            )

        self._check_feature_unlocks(distinction_entries, by_id)
        return labels

    @staticmethod
    def _check_feature_unlocks(
        distinction_entries: list[dict], by_id: dict[int, Distinction]
    ) -> None:
        """Raise unless every axis pick sits on a feature the payload also unlocks.

        Called by ``_resolve_sync_features``. ``sync`` replaces the draft's whole
        CHOICE list, so "already unlocked" can only mean "unlocked in this payload";
        a client that drops the unlock and keeps the axes is asking for an axis on a
        feature that is no longer distinctive.
        """
        opened = {
            (e["feature_trait"], e["feature_marking"])
            for e in distinction_entries
            if by_id[e["id"]].opens_feature
        }
        for entry in distinction_entries:
            distinction = by_id[entry["id"]]
            if not distinction.requires_feature_opened:
                continue
            if (entry["feature_trait"], entry["feature_marking"]) not in opened:
                raise ValidationError(
                    {"detail": (f"{distinction.name} needs that feature made distinctive first.")}
                )

    def _validate_bulk_exclusions(self, distinctions: list[Distinction]) -> None:
        """
        Validate that no mutual exclusions exist between the selected distinctions.

        Raises:
            ValidationError: If any conflicts exist.
        """
        distinction_ids = {d.id for d in distinctions}
        distinctions_by_id = {d.id: d for d in distinctions}

        for distinction in distinctions:
            # Check mutual exclusions (uses prefetched cached_mutually_exclusive_with)
            excluded_ids = {d.id for d in distinction.cached_mutually_exclusive_with}
            conflicts = distinction_ids & excluded_ids
            if conflicts:
                conflicting = distinctions_by_id.get(next(iter(conflicts)))
                msg = f"{distinction.name} is mutually exclusive with {conflicting.name}."
                raise ValidationError(
                    {"detail": msg, "conflicting_ids": [distinction.id, conflicting.id]}
                )

            # Check variant exclusions (uses prefetched cached_variants on parent)
            parent = distinction.parent_distinction
            if parent and parent.variants_are_mutually_exclusive:
                sibling_ids = {v.id for v in parent.cached_variants if v.id != distinction.id}
                conflicts = distinction_ids & sibling_ids
                if conflicts:
                    conflicting = distinctions_by_id.get(next(iter(conflicts)))
                    raise ValidationError(
                        {
                            "detail": f"Can only select one {parent.name} variant.",
                            "conflicting_ids": [distinction.id, conflicting.id],
                        }
                    )
