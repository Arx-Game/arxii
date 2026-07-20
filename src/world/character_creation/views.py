"""
Character Creation API views.
"""

from http import HTTPMethod
import logging
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

from django.db.models import Case, IntegerField, Prefetch, QuerySet, Value, When
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer, Serializer
from rest_framework.views import APIView

from world.character_creation.constants import (
    UNBOUND_DRAWBACK_DISTINCTION_SLUG,
    ApplicationStatus,
)
from world.character_creation.filters import (
    CGGiftOptionFilter,
    CGTechniqueOptionFilter,
    FamilyFilter,
    GenderFilter,
    GlimpseTagFilter,
    PathFilter,
    PronounsFilter,
    SpeciesFilter,
    TraditionFilter,
)
from world.character_creation.models import (
    Beginnings,
    BeginningTradition,
    CGPointBudget,
    CharacterDraft,
    DraftApplication,
    OriginTemplate,
    OriginTemplateSlot,
    StartingArea,
)
from world.character_creation.serializers import (
    BeginningsSerializer,
    CGExplanationsSerializer,
    CGGiftOptionSerializer,
    CGGlimpseTagSerializer,
    CGOriginTemplateSerializer,
    CGPointBudgetSerializer,
    CGTechniqueOptionSerializer,
    CharacterDraftCreateSerializer,
    CharacterDraftSerializer,
    ClaimableTitleSerializer,
    DraftApplicationCommentSerializer,
    DraftApplicationDetailSerializer,
    DraftApplicationSerializer,
    GenderSerializer,
    HouseClaimStatusSerializer,
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
from world.codex.models import BeginningsCodexGrant, PathCodexGrant
from world.forms.services import get_cg_form_options
from world.magic.models import (
    Gift,
    GlimpseTag,
    GlimpseTagDistinctionSuggestion,
    Technique,
    Tradition,
)
from world.magic.services.cg_catalog import get_gift_options, get_technique_options
from world.magic.types.cg_catalog import TechniqueOptions
from world.roster.models import Family
from world.roster.serializers import FamilySerializer
from world.species.models import Language, Species, SpeciesStatBonus
from world.stories.pagination import StandardResultsSetPagination

logger = logging.getLogger(__name__)


class StartingAreaViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for listing starting areas."""

    pagination_class = None  # 2026-07 audit: opt out of default paginator (ADR-0138)

    # Schema-introspection sentinel (drf-spectacular): with only a dynamic
    # get_queryset, the id path-param type is inferred differently per
    # environment (string locally vs integer in CI), so api-types-drift
    # flapped. Runtime always uses get_queryset below.
    queryset = StartingArea.objects.none()

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

    pagination_class = None  # 2026-07 audit: opt out of default paginator (ADR-0138)

    serializer_class = BeginningsSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["starting_area"]

    def get_queryset(self) -> QuerySet[Beginnings]:
        """Return beginnings filtered by availability and access."""
        queryset = (
            Beginnings.objects.filter(is_active=True)
            .select_related("starting_area")
            .prefetch_related(
                Prefetch(
                    "allowed_species",
                    queryset=Species.objects.all(),
                    to_attr="cached_allowed_species",
                ),
                Prefetch(
                    "starting_languages",
                    queryset=Language.objects.all(),
                    to_attr="cached_starting_languages",
                ),
                Prefetch(
                    "codex_grants",
                    queryset=BeginningsCodexGrant.objects.only("beginnings_id", "entry_id"),
                    to_attr="cached_codex_grants",
                ),
            )
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

    pagination_class = None  # 2026-07 audit: opt out of default paginator (ADR-0138)

    queryset = Species.objects.select_related("parent", "codex_entry").prefetch_related(
        Prefetch(
            "stat_bonuses",
            queryset=SpeciesStatBonus.objects.all(),
            to_attr="cached_stat_bonuses",
        ),
    )
    serializer_class = SpeciesSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = SpeciesFilter


class FamilyViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for listing families.

    Filter by area_id to get families available for a starting area's realm.
    """

    pagination_class = None  # 2026-07 audit: opt out of default paginator (ADR-0138)

    queryset = Family.objects.filter(is_playable=True)
    serializer_class = FamilySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = FamilyFilter


class GenderViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for listing gender options."""

    pagination_class = None  # 2026-07 audit: opt out of default paginator (ADR-0138)

    queryset = Gender.objects.all()
    serializer_class = GenderSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = GenderFilter


class PronounsViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for listing pronoun sets."""

    pagination_class = None  # 2026-07 audit: opt out of default paginator (ADR-0138)

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

    pagination_class = None  # 2026-07 audit: opt out of default paginator (ADR-0138)

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

    pagination_class = None  # 2026-07 audit: opt out of default paginator (ADR-0138)

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
        codex_grants_prefetch = Prefetch(
            "codex_grants",
            queryset=PathCodexGrant.objects.only("path_id", "entry_id"),
            to_attr="cached_codex_grants",
        )
        return (
            Path.objects.filter(stage=PathStage.PROSPECT, is_active=True)
            .prefetch_related(path_aspects_prefetch, codex_grants_prefetch)
            .order_by("sort_order", "name")
        )


def _view_request(view: viewsets.GenericViewSet) -> Request | None:
    """Return ``view.request``, or None during drf-spectacular schema generation.

    Shared by every CG ViewSet below that resolves its queryset from a query
    param — a single suppression site instead of one per call site.
    """
    return getattr(view, "request", None)  # noqa: GETATTR_LITERAL


class TraditionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Lists traditions available for a beginning during CG.

    Query params:
        beginning_id: Filter by beginning (required)
    """

    pagination_class = None  # 2026-07 audit: opt out of default paginator (ADR-0138)

    serializer_class = TraditionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = TraditionFilter

    def _get_beginning(self) -> Beginnings | None:
        """Resolve the request's Beginnings via SharedMemoryModel identity map.

        After first load per process, ``Beginnings.objects.get(pk=N)`` is a
        cache hit (zero queries). The Beginning then owns all per-Beginning
        cached state we care about — most importantly
        ``cached_beginning_traditions`` — which means there's no need (and
        no place) to cache anything on the viewset itself.

        ``query_params`` returns the id as a string, but Evennia's identity
        map keys instances by int pk; cast explicitly so the cache hits.
        """
        request = _view_request(self)
        raw = (
            request.query_params.get("beginning_id")  # noqa: USE_FILTERSET
            if request is not None
            else None
        )
        if not raw:
            return None
        try:
            beginning_id = int(raw)
        except (TypeError, ValueError):
            return None
        try:
            return Beginnings.objects.get(pk=beginning_id)
        except Beginnings.DoesNotExist:
            return None

    def get_queryset(self) -> QuerySet[Tradition]:
        beginning = self._get_beginning()
        if beginning is None:
            return Tradition.objects.none()

        # ``cached_beginning_traditions`` lives on the SharedMemoryModel-cached
        # Beginning instance. The same data is returned to every caller asking
        # about this Beginning, so the SharedMemoryModel cache is the right
        # location: populated once per Beginning per process, then free.
        bts = beginning.cached_beginning_traditions
        ordered_ids = [bt.tradition_id for bt in bts]
        if not ordered_ids:
            return Tradition.objects.none()

        # Tradition rows are already loaded as ``bt.tradition`` via
        # select_related on the cached BT list. We return a real queryset
        # (so DRF pagination/filtering keeps working), but identity map
        # makes the underlying instances free — only the row enumeration
        # touches the DB.
        order_case = Case(
            *[When(id=tid, then=Value(idx)) for idx, tid in enumerate(ordered_ids)],
            default=Value(len(ordered_ids)),
            output_field=IntegerField(),
        )
        return (
            Tradition.objects.filter(id__in=ordered_ids, is_active=True)
            .annotate(_bt_order=order_case)
            .order_by("_bt_order", "name")
        )

    def get_serializer_context(self) -> dict[str, Any]:
        context = super().get_serializer_context()
        beginning = self._get_beginning()
        context["beginning_id"] = beginning.pk if beginning is not None else None
        # Build the per-Tradition BT lookup from the Beginning's cached list.
        # No new queries — the BT rows are already in memory via the cached_property.
        context["beginning_traditions_by_tradition"] = (
            {bt.tradition_id: bt for bt in beginning.cached_beginning_traditions}
            if beginning is not None
            else {}
        )
        return context


class CGGiftOptionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    List gifts pickable for a draft's chosen tradition + path during CG (#2426).

    Query params:
        draft_id: The caller's CharacterDraft (required — empty list without it).

    Empty list until the draft has both a selected tradition and a selected path.
    Delegates availability resolution to ``world.magic.services.cg_catalog
    .get_gift_options`` — a gift with zero combined (path pool ∪ tradition
    signature) techniques for this path is excluded.
    """

    serializer_class = CGGiftOptionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # Small lookup table.
    filter_backends = [DjangoFilterBackend]
    filterset_class = CGGiftOptionFilter

    def filter_queryset(self, queryset: QuerySet[Gift]) -> QuerySet[Gift]:
        """Skip ``CGGiftOptionFilter``'s form validation — it exists only for OpenAPI
        schema/discoverability (see its docstring); real ``draft_id`` resolution
        (including malformed-value handling) already happened in ``get_queryset()``
        via ``_get_draft()``. Without this override, ``NumberFilter`` form validation
        would 400 a non-numeric ``draft_id`` instead of treating it as absent like
        every other malformed/missing param on this endpoint.
        """
        return queryset

    def _get_draft(self) -> CharacterDraft | None:
        """Resolve the request's own CharacterDraft from ``?draft_id=``."""
        request = _view_request(self)
        if request is None:
            return None
        raw = request.query_params.get("draft_id")  # noqa: USE_FILTERSET
        if not raw:
            return None
        try:
            draft_id = int(raw)
        except (TypeError, ValueError):
            return None
        return get_object_or_404(CharacterDraft, pk=draft_id, account=request.user)

    def get_queryset(self) -> QuerySet[Gift]:
        """Return gifts pickable under the draft's tradition, available to its path."""
        draft = self._get_draft()
        if draft is None:
            return Gift.objects.none()
        if draft.selected_tradition_id is None or draft.selected_path_id is None:
            return Gift.objects.none()

        gift_ids = [
            gift.id for gift in get_gift_options(draft.selected_tradition, draft.selected_path)
        ]
        return Gift.objects.filter(id__in=gift_ids).select_related("codex_entry").order_by("name")


class CGTechniqueOptionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    List technique options (pool U signature) for a draft's (path, gift, tradition)
    pick during CG (#2426).

    Query params:
        draft_id: The caller's CharacterDraft (required).
        gift_id: The Gift being picked techniques for (required).

    Empty list until both params resolve to a draft with tradition + path selected.
    Delegates to ``world.magic.services.cg_catalog.get_technique_options``; each
    returned row's ``is_signature`` reflects membership in the tradition's curated
    signature set (as opposed to the path's starter pool).
    """

    serializer_class = CGTechniqueOptionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # Small lookup table.
    filter_backends = [DjangoFilterBackend]
    filterset_class = CGTechniqueOptionFilter

    def filter_queryset(self, queryset: QuerySet[Technique]) -> QuerySet[Technique]:
        """Skip ``CGTechniqueOptionFilter``'s form validation — it exists only for
        OpenAPI schema/discoverability (see its docstring); real ``draft_id``/``gift_id``
        resolution (including malformed-value handling) already happened in
        ``get_queryset()`` via ``_resolve_options()``. Without this override,
        ``NumberFilter`` form validation would 400 a non-numeric id instead of treating
        it as absent like every other malformed/missing param on this endpoint.
        """
        return queryset

    def _resolve_options(self) -> TechniqueOptions | None:
        """Resolve pool/signature techniques for ``?draft_id=&gift_id=``, cached per request."""
        if hasattr(self, "_cg_technique_options"):
            return self._cg_technique_options

        request = _view_request(self)
        raw_draft_id = None
        raw_gift_id = None
        if request is not None:
            raw_draft_id = request.query_params.get("draft_id")  # noqa: USE_FILTERSET
            raw_gift_id = request.query_params.get("gift_id")  # noqa: USE_FILTERSET
        options: TechniqueOptions | None = None
        if raw_draft_id and raw_gift_id:
            try:
                draft_id = int(raw_draft_id)
                gift_id = int(raw_gift_id)
            except (TypeError, ValueError):
                draft_id = None
                gift_id = None
            if draft_id is not None and gift_id is not None:
                draft = get_object_or_404(CharacterDraft, pk=draft_id, account=request.user)
                if draft.selected_tradition_id is not None and draft.selected_path_id is not None:
                    gift = get_object_or_404(Gift, pk=gift_id)
                    options = get_technique_options(
                        draft.selected_path, gift, draft.selected_tradition
                    )

        self._cg_technique_options = options
        return options

    def get_queryset(self) -> QuerySet[Technique]:
        """Return the pool U signature techniques for the resolved (path, gift, tradition)."""
        options = self._resolve_options()
        if options is None:
            return Technique.objects.none()

        technique_ids = {t.id for t in [*options.pool, *options.signature]}
        return Technique.objects.filter(id__in=technique_ids).select_related("effect_type")

    def get_serializer_context(self) -> dict[str, Any]:
        context = super().get_serializer_context()
        options = self._resolve_options()
        context["signature_technique_ids"] = (
            {t.id for t in options.signature} if options is not None else set()
        )
        return context


class CGGlimpseTagViewSet(viewsets.ReadOnlyModelViewSet):
    """
    List active glimpse tags for the CG guided glimpse flow (#2427).

    Global authored catalog — not draft-dependent, so it also serves the
    post-CG "finish your glimpse later" surface on the character sheet.
    """

    serializer_class = CGGlimpseTagSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # Small lookup table.
    filter_backends = [DjangoFilterBackend]
    filterset_class = GlimpseTagFilter

    def get_queryset(self) -> QuerySet[GlimpseTag]:
        return GlimpseTag.objects.filter(is_active=True).prefetch_related(
            Prefetch(
                "distinction_suggestions",
                queryset=GlimpseTagDistinctionSuggestion.objects.select_related("distinction"),
                to_attr="cached_distinction_suggestions",
            )
        )


class CGOriginTemplateViewSet(viewsets.ReadOnlyModelViewSet):
    """List active origin-story templates for the CG guided flow (#2478).

    Filter by ``beginning`` to get templates available for a specific beginning.
    Mirrors ``CGGlimpseTagViewSet``.
    """

    pagination_class = None  # ADR-0138: opt out of default paginator
    serializer_class = CGOriginTemplateSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["beginning"]

    def get_queryset(self) -> QuerySet[OriginTemplate]:
        """Return active templates with prefetched slots, ordered."""
        return (
            OriginTemplate.objects.filter(is_active=True)
            .prefetch_related(
                Prefetch(
                    "slots",
                    queryset=OriginTemplateSlot.objects.order_by("sort_order"),
                    to_attr="cached_slots",
                )
            )
            .order_by("sort_order", "name")
        )


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

    pagination_class = None  # 2026-07 audit: opt out of default paginator (ADR-0138)

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
            character = finalize_character(
                draft,
                add_to_roster=True,
                created_by_account=cast("AccountDB", request.user),
            )
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

    @action(detail=True, methods=[HTTPMethod.POST], url_path="finalize-gm")
    def finalize_gm(self, request: Request, pk: int | None = None) -> Response:
        """Finalize a player-GM's character onto the Available roster for their table (#1506).

        The requesting account must own the target GM table. Creates the character + a
        Story tied to the table, and stamps the roster entry with GM_TABLE provenance — a
        viewable quality/trust signal (the GM vouches for it for their table; apping is
        never gated by it). Body: ``target_table`` (id, required), ``story_title``
        (required), optional ``story_description``.
        """
        from django.core.exceptions import ValidationError as DjangoValidationError  # noqa: PLC0415

        from world.character_creation.services import finalize_gm_character  # noqa: PLC0415
        from world.gm.models import GMTable  # noqa: PLC0415

        table_id = request.data.get("target_table")
        story_title = (request.data.get("story_title") or "").strip()
        if table_id is None or not story_title:
            return Response(
                {"detail": "target_table and story_title are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        table = GMTable.objects.filter(pk=table_id).first()
        if table is None:
            return Response(
                {"detail": "That GM table does not exist."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if table.gm.account_id != request.user.id:
            return Response(
                {"detail": "You do not own that GM table."},
                status=status.HTTP_403_FORBIDDEN,
            )

        draft = self.get_object()
        draft.is_gm_creation = True
        draft.target_table = table
        draft.story_title = story_title
        draft.story_description = request.data.get("story_description", "") or ""
        draft.save(
            update_fields=["is_gm_creation", "target_table", "story_title", "story_description"]
        )

        try:
            entry, story = finalize_gm_character(draft)
        except DjangoValidationError as exc:
            return Response(
                {"detail": "; ".join(exc.messages)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {
                "character_id": entry.character_sheet.pk,
                "roster_entry_id": entry.pk,
                "story_id": story.pk,
                "message": "GM character created on the Available roster.",
            },
            status=status.HTTP_201_CREATED,
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
        """Select a tradition for the draft.

        Gates on ``BeginningTradition.required_distinction`` (#2426): a tradition
        that requires formal training may only be selected once the draft already
        holds that distinction (added via the distinctions app). There is no
        general auto-attach — `world.distinctions.views` only *clears* the selected
        tradition when its required distinction is later removed
        (`_clear_tradition_if_required_distinction_removed`); it never adds one.

        **One deliberate exception (#2442):** the "Unbound" drawback distinction
        (``UNBOUND_DRAWBACK_DISTINCTION_SLUG``) IS auto-added when missing, instead
        of rejecting the request. Unbound is CG's tradition-agnostic default (#2426)
        — unlike Orphaned Tradition (a deliberate story pick, #2428 Task 5), a
        player must not be forced to already know about this one specific drawback
        before CG can complete; see
        ``world.seeds.tests.test_playable_slice.TestSeededCharacterCreation
        .test_tradition_step_completable_for_every_seeded_beginning`` for the
        "CG must remain completable via the Unbound path with zero manual steps"
        regression proof #2426 shipped, which this exception preserves.
        """
        from world.distinctions.types import build_distinction_entry  # noqa: PLC0415

        draft = self.get_object()
        tradition_id = request.data.get("tradition_id")

        if tradition_id is None:
            draft.selected_tradition = None
            draft.save(update_fields=["selected_tradition"])
            return Response({"status": "tradition cleared"})

        if not draft.selected_beginnings:
            raise ValidationError({"detail": "A beginning must be selected first."})

        bt = BeginningTradition.objects.filter(
            beginning=draft.selected_beginnings, tradition_id=tradition_id
        ).first()
        if bt is None:
            raise ValidationError(
                {"detail": "This tradition is not available for the selected beginning."}
            )

        update_fields = ["selected_tradition"]
        if bt.required_distinction_id:
            distinctions = draft.draft_data.get("distinctions", [])
            held_distinction_ids = {entry.get("distinction_id") for entry in distinctions}
            if bt.required_distinction_id not in held_distinction_ids:
                if bt.required_distinction.slug == UNBOUND_DRAWBACK_DISTINCTION_SLUG:
                    distinctions.append(build_distinction_entry(bt.required_distinction, rank=1))
                    draft.draft_data["distinctions"] = distinctions
                    update_fields.append("draft_data")
                else:
                    raise ValidationError(
                        {
                            "detail": (
                                "This tradition requires formal training "
                                "(take its distinction first)."
                            )
                        }
                    )

        tradition = get_object_or_404(Tradition, pk=tradition_id, is_active=True)
        draft.selected_tradition = tradition
        draft.save(update_fields=update_fields)

        serializer = self.get_serializer(draft)
        return Response(serializer.data)

    @extend_schema(responses=HouseClaimStatusSerializer)
    @action(detail=True, methods=[HTTPMethod.GET, HTTPMethod.POST], url_path="house-claim")
    def house_claim(self, request: Request, pk: int | None = None) -> Response:
        """GET the draft's house claim; POST to submit one (#1884 Phase D).

        POST body: title (id), template (id), house_name, backstory,
        principles (mercy/method/status/change/allegiance/power ints).
        The automated thematic gates run here; staff review follows in admin.
        """
        from world.societies.houses.creator import submit_house_claim  # noqa: PLC0415
        from world.societies.houses.models import HouseClaim, HouseTemplate, Title  # noqa: PLC0415
        from world.societies.houses.services import HousesServiceError  # noqa: PLC0415

        draft = self.get_object()
        if request.method == "GET":
            claim = HouseClaim.objects.filter(draft=draft).first()
            if claim is None:
                return Response({"detail": "No house claim."}, status=status.HTTP_404_NOT_FOUND)
            return Response(HouseClaimStatusSerializer(claim).data)

        title = Title.objects.filter(pk=request.data.get("title")).first()
        template = HouseTemplate.objects.filter(pk=request.data.get("template")).first()
        if title is None or template is None:
            return Response(
                {"detail": "Unknown title or template."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        principles = {
            axis: int(request.data.get(axis, 0))
            for axis in ("mercy", "method", "status", "change", "allegiance", "power")
        }
        raw_aspects = request.data.get("aspects", [])
        aspect_picks: dict[int, list[int]] = {}
        if isinstance(raw_aspects, list):
            for entry in raw_aspects:
                if not isinstance(entry, dict):
                    continue
                try:
                    definition_id = int(entry.get("definition"))
                    option_ids = [int(option) for option in entry.get("options", [])]
                except (TypeError, ValueError):
                    return Response(
                        {"detail": "Malformed aspects payload."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                aspect_picks[definition_id] = option_ids
        try:
            claim = submit_house_claim(
                draft=draft,
                title=title,
                template=template,
                house_name=str(request.data.get("house_name", "")),
                backstory=str(request.data.get("backstory", "")),
                principles=principles,
                words=str(request.data.get("words", "")),
                colors=str(request.data.get("colors", "")),
                sigil_description=str(request.data.get("sigil_description", "")),
                lands_writeup=str(request.data.get("lands_writeup", "")),
                aspect_picks=aspect_picks,
            )
        except HousesServiceError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(HouseClaimStatusSerializer(claim).data, status=status.HTTP_201_CREATED)

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
        from world.character_creation.models import DraftApplicationComment  # noqa: PLC0415

        return (
            DraftApplication.objects.select_related("draft__account", "player_account", "reviewer")
            .prefetch_related(
                Prefetch(
                    "comments",
                    queryset=DraftApplicationComment.objects.select_related("author"),
                    to_attr="cached_comments",
                ),
            )
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


class ClaimableTitleViewSet(viewsets.ReadOnlyModelViewSet):
    """Vacant set-aside titles open to CG house definition (#1884 Phase D)."""

    permission_classes = [IsAuthenticated]
    pagination_class = None
    filter_backends: list = []
    serializer_class = ClaimableTitleSerializer

    def get_queryset(self) -> QuerySet:
        from world.societies.houses.models import Title  # noqa: PLC0415

        return (
            Title.objects.filter(is_claimable=True, house__isnull=True, holder__isnull=True)
            .select_related("realm", "seat_domain")
            .order_by("realm", "tier", "name")
        )
