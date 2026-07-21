"""API ViewSets for items."""

from dataclasses import dataclass
from http import HTTPMethod
from typing import Any, cast

from django.db.models import Prefetch, QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiTypes,
    extend_schema,
    inline_serializer,
)
from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB
from rest_framework import filters, mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet

from core_management.permissions import PlayerOrStaffPermission
from world.character_sheets.models import CharacterSheet
from world.items.exceptions import (
    CraftingNotConfigured,
    ItemError,
)
from world.items.filters import (
    FashionPresentationFilter,
    InteractionTypeFilter,
    ItemTemplateFilter,
    QualityTierFilter,
    VisibleWornItemFilter,
)
from world.items.models import (
    EquippedItem,
    FashionPresentation,
    InteractionType,
    ItemFacet,
    ItemInstance,
    ItemTemplate,
    Outfit,
    OutfitSlot,
    QualityTier,
    ReclamationClaim,
    Style,
    TemplateInteraction,
    TemplateSlot,
)
from world.items.serializers import (
    CraftableTemplateSerializer,
    CraftingQuoteSerializer,
    EquippedItemReadSerializer,
    FacetCraftResultSerializer,
    FashionJudgementSerializer,
    FashionPresentationSerializer,
    InteractionTypeSerializer,
    ItemFacetReadSerializer,
    ItemFacetWriteSerializer,
    ItemInstanceReadSerializer,
    ItemStyleWriteSerializer,
    ItemTemplateDetailSerializer,
    ItemTemplateListSerializer,
    OutfitReadSerializer,
    OutfitRenameSerializer,
    OutfitSlotReadSerializer,
    OutfitSlotWriteSerializer,
    OutfitWriteSerializer,
    PresentationEndorsementSerializer,
    QualityTierSerializer,
    StyleCraftResultSerializer,
    StyleSerializer,
    UseItemResultSerializer,
    UseItemSerializer,
    VisibleWornItemSerializer,
)
from world.items.services.appearance import LAYER_RANK, visible_worn_items_for
from world.items.services.usage import use_item
from world.magic.services.auth import _resolve_actor_sheet
from world.roster.models import RosterEntry

# Shared validation message for missing required query parameters across the
# item-first viewsets (these are computed/permission-context params, not
# queryset filters, so they're validated manually rather than via a FilterSet).
REQUIRED_QUERY_PARAM_MESSAGE = "This query parameter is required."

# Shared error detail for unknown reclamation claims.
_UNKNOWN_CLAIM_MSG = "Unknown claim."


def _user_plays_pk(user: AccountDB, pk: int) -> bool:
    """True if ``user`` has an active roster tenure on the character_sheet at ``pk``.

    Character pk equals CharacterSheet pk by construction
    (``CharacterSheet.character = OneToOneField(primary_key=True)``), so this
    helper covers both "does the user play this Character?" and "does the
    user play this CharacterSheet?" without needing two helpers.
    """
    return RosterEntry.objects.for_account(user).filter(character_sheet_id=pk).exists()


def _user_holds_item(user: AccountDB, item: ItemInstance) -> bool:
    """True if ``user`` plays the body (CharacterSheet) that holds ``item``.

    Items belong to characters (the body), not accounts; a user holds an
    item iff they have an active roster tenure on the
    ``holder_character_sheet``. Returns False for unowned items
    (holder_character_sheet is null).
    """
    if item.holder_character_sheet_id is None:
        return False
    return _user_plays_pk(user, item.holder_character_sheet_id)


class ItemFacetWritePermission(PlayerOrStaffPermission):
    """Allow attach/remove only if the user owns the item_instance, or is staff."""

    def has_permission_for_player(self, request: Request, view: APIView) -> bool:
        # POST: check the item_instance the request is targeting.
        if request.method == "POST":
            instance_pk = request.data.get("item_instance")
            if instance_pk is None:
                # If item_instance is absent or unparseable, fall through to True;
                # the serializer's required-field validation will reject.
                return True
            # #684: ownership lives on the body (CharacterSheet). An account
            # may play multiple characters; the permission allows any item
            # held by a body the user has active roster tenure on.
            user = cast(AccountDB, request.user)
            return ItemInstance.objects.filter(
                pk=instance_pk,
                holder_character_sheet_id__in=RosterEntry.objects.for_account(user).values(
                    "character_sheet_id"
                ),
            ).exists()
        return True  # DELETE checked at object level

    def has_object_permission_for_player(
        self, request: Request, view: APIView, obj: ItemFacet
    ) -> bool:
        return _user_holds_item(cast(AccountDB, request.user), obj.item_instance)


class ItemStyleWritePermission(PlayerOrStaffPermission):
    """Allow style-attach only if the user owns the item_instance, or is staff."""

    def has_permission_for_player(self, request: Request, view: APIView) -> bool:
        # POST: check the item_instance the request is targeting.
        if request.method == "POST":
            instance_pk = request.data.get("item_instance")
            if instance_pk is None:
                return True
            user = cast(AccountDB, request.user)
            return ItemInstance.objects.filter(
                pk=instance_pk,
                holder_character_sheet_id__in=RosterEntry.objects.for_account(user).values(
                    "character_sheet_id"
                ),
            ).exists()
        return True

    def has_object_permission_for_player(
        self, request: Request, view: APIView, obj: object
    ) -> bool:
        return True


class ItemTemplatePagination(PageNumberPagination):
    """Pagination for item template listings."""

    page_size = 50


def _paginated_response(
    item_serializer_cls: type[serializers.Serializer],
) -> serializers.Serializer:
    """Build an ``inline_serializer`` describing DRF's paginated wrapper.

    The five item-first viewsets all return ``paginator.get_paginated_response(...)``
    which wraps the serialized list as ``{count, next, previous, results}``.
    Declaring the same shape to drf-spectacular gives the frontend an
    accurate generated type instead of a bare-array lie.
    """
    return inline_serializer(
        name=f"Paginated{item_serializer_cls.__name__.replace('Serializer', '')}List",
        fields={
            "count": serializers.IntegerField(),
            "next": serializers.URLField(allow_null=True),
            "previous": serializers.URLField(allow_null=True),
            "results": item_serializer_cls(many=True),
        },
    )


class QualityTierViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only ViewSet for quality tier lookup data."""

    queryset = QualityTier.objects.all()
    serializer_class = QualityTierSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    filter_backends = [DjangoFilterBackend]
    filterset_class = QualityTierFilter


class StyleViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only ViewSet for the Style catalog (#2030).

    Player-facing lookup for the Motif style-binding picker.
    """

    queryset = Style.objects.all()
    serializer_class = StyleSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = ItemTemplatePagination
    filter_backends = [filters.SearchFilter]
    search_fields = ["name"]


class InteractionTypeViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only ViewSet for interaction type lookup data."""

    queryset = InteractionType.objects.order_by("label")
    serializer_class = InteractionTypeSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    filter_backends = [DjangoFilterBackend]
    filterset_class = InteractionTypeFilter


class ItemTemplateViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only ViewSet for item templates."""

    permission_classes = [IsAuthenticated]
    pagination_class = ItemTemplatePagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = ItemTemplateFilter

    def get_queryset(self) -> QuerySet[ItemTemplate]:
        """Return active templates only, with prefetch for detail views."""
        qs = ItemTemplate.objects.filter(is_active=True).select_related("image").order_by("name")
        if self.action == "retrieve":
            qs = qs.select_related("minimum_quality_tier", "image").prefetch_related(
                Prefetch(
                    "slots",
                    queryset=TemplateSlot.objects.all(),
                    to_attr="cached_slots",
                ),
                Prefetch(
                    "interaction_bindings",
                    queryset=TemplateInteraction.objects.select_related(
                        "interaction_type",
                    ),
                    to_attr="cached_interaction_bindings",
                ),
            )
        return qs

    def get_serializer_class(self) -> type[serializers.ModelSerializer]:
        """Use detail serializer for retrieve, list serializer for list."""
        if self.action == "retrieve":
            return ItemTemplateDetailSerializer
        return ItemTemplateListSerializer


@extend_schema(tags=["items"])
class ItemFacetViewSet(viewsets.ViewSet):
    """ViewSet for ItemFacet attach/list/delete.

    Item-first / item-scoped shape:

    - ``item_instance`` query parameter is REQUIRED for list.
    - List/retrieve return 404 unless the requester owns the item or
      is staff.
    - Walks ``item.cached_item_facets`` for list (one prefetch on cold
      load, zero on warm cache).
    """

    http_method_names = ["get", "post", "delete", "head", "options"]
    permission_classes = [ItemFacetWritePermission]
    # ``serializer_class`` is the default read shape — drf-spectacular uses
    # it for schema introspection on ``viewsets.ViewSet``. Write actions
    # override request/response via ``@extend_schema`` decorators.
    serializer_class = ItemFacetReadSerializer

    @extend_schema(
        responses=_paginated_response(ItemFacetReadSerializer),
        parameters=[
            OpenApiParameter(
                name="item_instance",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=True,
                description="ItemInstance pk whose facets to list.",
            ),
        ],
    )
    def list(self, request: Request) -> Response:
        """Return ItemFacet rows for ``?item_instance=<pk>``."""
        user = cast(AccountDB, request.user)
        # noqa: USE_FILTERSET
        instance_pk = _parse_int_param(request.query_params.get("item_instance"))  # noqa: USE_FILTERSET
        if instance_pk is None:
            raise serializers.ValidationError({"item_instance": REQUIRED_QUERY_PARAM_MESSAGE})
        try:
            item = (
                ItemInstance.objects.select_related("holder_character_sheet__character")
                .prefetch_related(
                    Prefetch(
                        "item_facets",
                        queryset=ItemFacet.objects.select_related(
                            "facet",
                            "attachment_quality_tier",
                            "applied_by_account",
                        ),
                        to_attr="cached_item_facets",
                    ),
                )
                .get(pk=instance_pk)
            )
        except ItemInstance.DoesNotExist as exc:
            raise NotFound from exc

        if not user.is_staff and not _user_holds_item(user, item):
            raise NotFound

        rows = list(item.cached_item_facets)
        paginator = ItemTemplatePagination()
        page = paginator.paginate_queryset(rows, request, view=self)  # ty: ignore[invalid-argument-type]
        serializer = ItemFacetReadSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(responses=ItemFacetReadSerializer)
    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        """Return a single ItemFacet if the requester owns its item."""
        user = cast(AccountDB, request.user)
        row_pk = _parse_int_param(pk)
        if row_pk is None:
            raise NotFound
        try:
            row = ItemFacet.objects.select_related(
                "item_instance",
                "item_instance__holder_character_sheet__character",
                "facet",
                "attachment_quality_tier",
                "applied_by_account",
            ).get(pk=row_pk)
        except ItemFacet.DoesNotExist as exc:
            raise NotFound from exc

        if not user.is_staff and not _user_holds_item(user, row.item_instance):
            raise NotFound

        serializer = ItemFacetReadSerializer(row)
        return Response(serializer.data)

    @extend_schema(request=ItemFacetWriteSerializer, responses=FacetCraftResultSerializer)
    def create(self, request: Request) -> Response:
        """Roll the crafting check and (on success) attach the facet, via the Action."""
        from actions.definitions.crafting import AttachFacetAction  # noqa: PLC0415

        serializer = ItemFacetWriteSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        item_instance = serializer.validated_data["item_instance"]
        facet = serializer.validated_data["facet"]
        actor = item_instance.holder_character_sheet.character
        action_result = AttachFacetAction().run(
            actor=actor, item_instance=item_instance, facet=facet
        )
        if not action_result.success:
            raise serializers.ValidationError({"non_field_errors": [action_result.message]})
        result = action_result.data["result"]
        status_code = 201 if result.attached else 200
        return Response(FacetCraftResultSerializer(result).data, status=status_code)

    @extend_schema(
        responses=CraftingQuoteSerializer,
        parameters=[
            OpenApiParameter(
                name="item_instance",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=True,
                description="ItemInstance pk to quote the crafting cost for.",
            ),
            OpenApiParameter(
                name="facet",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Facet pk that would be attached.",
            ),
        ],
    )
    @action(detail=False, methods=[HTTPMethod.GET], url_path="quote")
    def quote(self, request: Request) -> Response:
        """Return a read-only cost+quality quote for attaching a facet (no mutation)."""
        from world.items.crafting.constants import CraftingRecipeKind  # noqa: PLC0415
        from world.items.crafting.services import build_crafting_quote  # noqa: PLC0415
        from world.magic.models import Facet  # noqa: PLC0415

        user = cast(AccountDB, request.user)
        instance_pk = _parse_int_param(request.query_params.get("item_instance"))  # noqa: USE_FILTERSET
        facet_pk = _parse_int_param(request.query_params.get("facet"))  # noqa: USE_FILTERSET
        if instance_pk is None:
            raise serializers.ValidationError({"item_instance": REQUIRED_QUERY_PARAM_MESSAGE})
        if facet_pk is None:
            raise serializers.ValidationError({"facet": REQUIRED_QUERY_PARAM_MESSAGE})
        try:
            item_instance = ItemInstance.objects.select_related(
                "holder_character_sheet__character"
            ).get(pk=instance_pk)
        except ItemInstance.DoesNotExist as exc:
            raise NotFound from exc
        if not user.is_staff and not _user_holds_item(user, item_instance):
            raise NotFound
        try:
            facet = Facet.objects.get(pk=facet_pk)
        except Facet.DoesNotExist as exc:
            raise NotFound from exc
        crafter_character = item_instance.holder_character_sheet.character
        crafter_character_sheet = item_instance.holder_character_sheet
        try:
            quote = build_crafting_quote(
                kind=CraftingRecipeKind.FACET_ATTACH,
                crafter_character=crafter_character,
                crafter_character_sheet=crafter_character_sheet,
                target=facet,
            )
        except CraftingNotConfigured as exc:
            raise serializers.ValidationError({"non_field_errors": [exc.user_message]}) from exc
        return Response(CraftingQuoteSerializer(quote).data)

    @extend_schema(responses={204: None})
    def destroy(self, request: Request, pk: str | None = None) -> Response:
        """Remove the facet via the service (which fires cache invalidation)."""
        row_pk = _parse_int_param(pk)
        if row_pk is None:
            raise NotFound
        try:
            row = ItemFacet.objects.select_related("item_instance").get(pk=row_pk)
        except ItemFacet.DoesNotExist as exc:
            raise NotFound from exc
        # Run object-level permission so non-owners are rejected with 403.
        self.check_object_permissions(request, row)
        from actions.definitions.crafting import DetachFacetAction  # noqa: PLC0415

        actor = row.item_instance.holder_character_sheet.character
        action_result = DetachFacetAction().run(actor=actor, item_facet=row)
        if not action_result.success:
            raise serializers.ValidationError({"non_field_errors": [action_result.message]})
        return Response(status=204)


@extend_schema(tags=["items"])
class ItemInstanceViewSet(viewsets.ViewSet):
    """Read-only listing of ItemInstance rows for a character's inventory.

    Item-first / character-scoped shape:

    - ``character`` query parameter is REQUIRED.
    - Non-staff users can only inspect inventory of characters they
      currently play (active roster tenure).
    - Walks ``character.carried_items`` cached handler — no DB query
      when warm.

    The wardrobe page uses this to render carried-but-not-worn items;
    the frontend filters out equipped items locally.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = ItemInstanceReadSerializer

    @extend_schema(
        responses=_paginated_response(ItemInstanceReadSerializer),
        parameters=[
            OpenApiParameter(
                name="character",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Character ObjectDB pk whose inventory to list.",
            ),
        ],
    )
    def list(self, request: Request) -> Response:
        """Return ItemInstance rows located on ``?character=<pk>``."""
        user = cast(AccountDB, request.user)
        # noqa: USE_FILTERSET
        character_pk = _parse_int_param(request.query_params.get("character"))  # noqa: USE_FILTERSET
        if character_pk is None:
            raise serializers.ValidationError({"character": REQUIRED_QUERY_PARAM_MESSAGE})
        try:
            character = ObjectDB.objects.get(pk=character_pk)
        except ObjectDB.DoesNotExist as exc:
            raise NotFound from exc

        if not user.is_staff and not _user_plays_pk(user, character.pk):
            raise NotFound

        # Exclude consumed/destroyed rows so used-up items leave the inventory.
        rows = [r for r in character.carried_items if r.destroyed_at is None]
        paginator = ItemTemplatePagination()
        page = paginator.paginate_queryset(rows, request, view=self)  # ty: ignore[invalid-argument-type]
        serializer = ItemInstanceReadSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(responses=ItemInstanceReadSerializer)
    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        """Return a single ItemInstance if the requester may view it."""
        user = cast(AccountDB, request.user)
        item_pk = _parse_int_param(pk)
        if item_pk is None:
            raise NotFound
        try:
            item = (
                ItemInstance.objects.in_play()
                .select_related(
                    "template",
                    "quality_tier",
                    "game_object",
                    "image",
                    "template__image",
                    "currency_instrument",
                )
                .prefetch_related(
                    Prefetch(
                        "item_facets",
                        queryset=ItemFacet.objects.select_related(
                            "facet",
                            "attachment_quality_tier",
                        ),
                        to_attr="cached_item_facets",
                    ),
                )
                .get(pk=item_pk)
            )
        except ItemInstance.DoesNotExist as exc:
            raise NotFound from exc

        if not user.is_staff:
            holder = item.game_object.db_location
            if holder is None or not _user_plays_pk(user, holder.pk):
                raise NotFound

        # No ``viewer_sheet`` context: this endpoint only ever shows the
        # requester their own items, where ``can_steal`` is trivially False.
        serializer = ItemInstanceReadSerializer(item)
        return Response(serializer.data)

    @extend_schema(request=UseItemSerializer, responses=UseItemResultSerializer)
    @action(detail=True, methods=[HTTPMethod.POST], url_path="use")
    def use(self, request: Request, pk: str | None = None) -> Response:
        """Use an item with an on-use pool: apply its effects (to self); consumables spend a charge.

        Owner-or-staff gated. Business logic lives entirely in ``use_item``;
        this view resolves the actor, enforces ownership, and maps
        ``ItemError`` to HTTP 400 (mirroring the facet write path). The REST
        surface does NOT accept a target — on-use effects apply to the holder
        only by design. Targeted use is handled by ``UseItemAction``, which
        carries proximity/prerequisite checks.
        """
        user = cast(AccountDB, request.user)
        item_pk = _parse_int_param(pk)
        if item_pk is None:
            raise NotFound
        try:
            item = (
                ItemInstance.objects.in_play()
                .select_related(
                    "template",
                    "template__on_use_pool",
                    "template__on_use_check_type",
                    "game_object",
                )
                .get(pk=item_pk)
            )
        except ItemInstance.DoesNotExist as exc:
            raise NotFound from exc
        if not user.is_staff and not _user_holds_item(user, item):
            raise NotFound
        if item.game_object is None:
            # A held consumable always has a game_object; guard against the
            # AttributeError→500 if that invariant is ever violated.
            raise NotFound
        actor = item.game_object.db_location  # the holder character (its game object)
        try:
            result = use_item(item_instance=item, user=actor)
        except ItemError as exc:
            raise serializers.ValidationError({"non_field_errors": [exc.user_message]}) from exc
        return Response(
            UseItemResultSerializer(
                {
                    "charges_remaining": result.charges_remaining,
                    "destroyed": result.destroyed,
                    "soft_deleted": result.soft_deleted,
                    "applied_effect_count": len(result.applied_effects),
                }
            ).data
        )


@extend_schema(tags=["items"])
class EquippedItemViewSet(viewsets.ViewSet):
    """Read-only ViewSet for EquippedItem (GET list/detail).

    Item-first / character-scoped shape:

    - ``character`` query parameter is REQUIRED for list.
    - Non-staff users can only see equipped items for characters they
      currently play (active roster tenure).
    - Walks ``character.equipped_items`` cached handler — no DB query
      when warm.

    Mutations (equip/unequip) flow through the unified action dispatcher
    via the ``execute_action`` websocket inputfunc — REST stays read-only.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = EquippedItemReadSerializer

    @extend_schema(
        responses=_paginated_response(EquippedItemReadSerializer),
        parameters=[
            OpenApiParameter(
                name="character",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Character ObjectDB pk whose equipment to list.",
            ),
        ],
    )
    def list(self, request: Request) -> Response:
        """Return equipped items for ``?character=<pk>``."""
        user = cast(AccountDB, request.user)
        # noqa: USE_FILTERSET
        character_pk = _parse_int_param(request.query_params.get("character"))  # noqa: USE_FILTERSET
        if character_pk is None:
            raise serializers.ValidationError({"character": REQUIRED_QUERY_PARAM_MESSAGE})
        try:
            character = ObjectDB.objects.get(pk=character_pk)
        except ObjectDB.DoesNotExist as exc:
            raise NotFound from exc

        if not user.is_staff and not _user_plays_pk(user, character.pk):
            raise NotFound  # don't leak existence

        rows = list(character.equipped_items)
        paginator = ItemTemplatePagination()
        page = paginator.paginate_queryset(rows, request, view=self)  # ty: ignore[invalid-argument-type]
        serializer = EquippedItemReadSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(responses=EquippedItemReadSerializer)
    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        """Return a single EquippedItem if the requester may view it."""
        user = cast(AccountDB, request.user)
        row_pk = _parse_int_param(pk)
        if row_pk is None:
            raise NotFound
        try:
            row = EquippedItem.objects.select_related(
                "item_instance",
                "item_instance__template",
                "character",
                "character__sheet_data",
            ).get(pk=row_pk)
        except EquippedItem.DoesNotExist as exc:
            raise NotFound from exc

        if not user.is_staff and not _user_plays_pk(user, row.character.pk):
            raise NotFound

        serializer = EquippedItemReadSerializer(row)
        return Response(serializer.data)


class OutfitWritePermission(PlayerOrStaffPermission):
    """Allow Outfit writes only if the user currently plays the character_sheet.

    Mirrors ``ItemFacetWritePermission`` shape. Object-level checks fall
    through to ``has_object_permission`` for PATCH/DELETE; POST validates
    by reading ``character_sheet`` from request data.
    """

    def has_permission_for_player(self, request: Request, view: APIView) -> bool:
        if request.method != "POST":
            # PATCH/DELETE delegated to has_object_permission.
            return True
        sheet_pk = request.data.get("character_sheet")
        if sheet_pk is None:
            # Serializer rejects missing field with 400 — defer there.
            return True
        try:
            sheet = CharacterSheet.objects.get(pk=sheet_pk)
        except (CharacterSheet.DoesNotExist, ValueError, TypeError):
            return True
        return _user_plays_pk(cast(AccountDB, request.user), sheet.pk)

    def has_object_permission_for_player(
        self, request: Request, view: APIView, obj: Outfit
    ) -> bool:
        return _user_plays_pk(cast(AccountDB, request.user), obj.character_sheet_id)


class OutfitSlotWritePermission(PlayerOrStaffPermission):
    """Allow OutfitSlot writes only if the user currently plays the outfit's sheet."""

    def has_permission_for_player(self, request: Request, view: APIView) -> bool:
        if request.method != "POST":
            return True
        outfit_pk = request.data.get("outfit")
        if outfit_pk is None:
            return True
        try:
            outfit = Outfit.objects.select_related("character_sheet").get(pk=outfit_pk)
        except (Outfit.DoesNotExist, ValueError, TypeError):
            return True
        return _user_plays_pk(cast(AccountDB, request.user), outfit.character_sheet_id)

    def has_object_permission_for_player(
        self, request: Request, view: APIView, obj: OutfitSlot
    ) -> bool:
        return _user_plays_pk(cast(AccountDB, request.user), obj.outfit.character_sheet_id)


@extend_schema(tags=["items"])
class OutfitViewSet(viewsets.ViewSet):
    """ViewSet for Outfit definitions (save / list / rename / delete).

    Item-first / sheet-scoped shape:

    - ``character_sheet`` query parameter is REQUIRED for list.
    - List walks ``sheet.saved_outfits`` cached handler.
    - Write actions delegate to existing serializers + services,
      gated by OutfitWritePermission.
    """

    permission_classes = [OutfitWritePermission]
    serializer_class = OutfitReadSerializer

    @extend_schema(
        responses=_paginated_response(OutfitReadSerializer),
        parameters=[
            OpenApiParameter(
                name="character_sheet",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=True,
                description="CharacterSheet pk whose saved outfits to list.",
            ),
        ],
    )
    def list(self, request: Request) -> Response:
        """Return outfits saved on ``?character_sheet=<pk>``."""
        user = cast(AccountDB, request.user)
        # noqa: USE_FILTERSET
        sheet_pk = _parse_int_param(request.query_params.get("character_sheet"))  # noqa: USE_FILTERSET
        if sheet_pk is None:
            raise serializers.ValidationError({"character_sheet": REQUIRED_QUERY_PARAM_MESSAGE})
        try:
            sheet = CharacterSheet.objects.get(pk=sheet_pk)
        except CharacterSheet.DoesNotExist as exc:
            raise NotFound from exc

        if not user.is_staff and not _user_plays_pk(user, sheet.pk):
            raise NotFound

        rows = list(sheet.saved_outfits)
        paginator = ItemTemplatePagination()
        page = paginator.paginate_queryset(rows, request, view=self)  # ty: ignore[invalid-argument-type]
        serializer = OutfitReadSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(responses=OutfitReadSerializer)
    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        """Return a single Outfit if the requester may view it."""
        user = cast(AccountDB, request.user)
        outfit_pk = _parse_int_param(pk)
        if outfit_pk is None:
            raise NotFound
        try:
            outfit = (
                Outfit.objects.select_related(
                    "character_sheet",
                    "wardrobe",
                    "wardrobe__template",
                )
                .prefetch_related(
                    Prefetch(
                        "slots",
                        queryset=OutfitSlot.objects.select_related(
                            "item_instance",
                            "item_instance__template",
                            "item_instance__quality_tier",
                            "item_instance__currency_instrument",
                        ),
                        to_attr="cached_outfit_slots",
                    ),
                )
                .get(pk=outfit_pk)
            )
        except Outfit.DoesNotExist as exc:
            raise NotFound from exc

        if not user.is_staff and not _user_plays_pk(user, outfit.character_sheet_id):
            raise NotFound

        serializer = OutfitReadSerializer(outfit)
        return Response(serializer.data)

    @extend_schema(request=OutfitWriteSerializer, responses=OutfitReadSerializer)
    def create(self, request: Request) -> Response:
        """Create an Outfit via SaveOutfitAction (validates via the existing serializer)."""
        from actions.definitions.outfits import SaveOutfitAction  # noqa: PLC0415

        serializer = OutfitWriteSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        sheet = serializer.validated_data["character_sheet"]
        wardrobe = serializer.validated_data["wardrobe"]
        name = serializer.validated_data["name"]
        description = serializer.validated_data.get("description", "")
        action_result = SaveOutfitAction().run(
            actor=sheet.character,
            wardrobe=wardrobe,
            name=name,
            description=description,
        )
        if not action_result.success:
            # Field-specific errors (e.g. "wardrobe") collapse to non_field_errors here —
            # SaveOutfitAction's ActionResult carries only a message, not the originating
            # field (#1866). Deliberate trade-off of routing through the Action layer.
            raise serializers.ValidationError({"non_field_errors": [action_result.message]})
        read = OutfitReadSerializer(action_result.data["outfit"])
        return Response(read.data, status=201)

    @extend_schema(request=OutfitRenameSerializer, responses=OutfitReadSerializer)
    def update(self, request: Request, pk: str | None = None) -> Response:
        """Full update (PUT) — rename/redescribe an outfit.

        Only ``name`` and ``description`` are mutable. ``character_sheet``
        and ``wardrobe`` are write-once (set at create time). See
        ``OutfitRenameSerializer`` for the accepted request shape.
        """
        return self._update(request, pk, partial=False)

    @extend_schema(request=OutfitRenameSerializer, responses=OutfitReadSerializer)
    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        """Partial update (PATCH) — rename/redescribe an outfit.

        Same field set as PUT (only ``name``/``description``).
        """
        return self._update(request, pk, partial=True)

    def _update(self, request: Request, pk: str | None, *, partial: bool) -> Response:
        from actions.definitions.outfits import RenameOutfitAction  # noqa: PLC0415

        outfit_pk = _parse_int_param(pk)
        if outfit_pk is None:
            raise NotFound
        try:
            outfit = Outfit.objects.select_related("character_sheet").get(pk=outfit_pk)
        except Outfit.DoesNotExist as exc:
            raise NotFound from exc
        self.check_object_permissions(request, outfit)
        serializer = OutfitRenameSerializer(
            outfit, data=request.data, partial=partial, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        name = serializer.validated_data.get("name", outfit.name)
        description = serializer.validated_data.get("description", outfit.description)
        actor = outfit.character_sheet.character
        action_result = RenameOutfitAction().run(
            actor=actor, outfit=outfit, name=name, description=description
        )
        if not action_result.success:
            # See the create() note above: RenameOutfitAction's ActionResult carries only
            # a message, not a field key, so any field-specific error collapses here.
            raise serializers.ValidationError({"non_field_errors": [action_result.message]})
        read = OutfitReadSerializer(outfit)
        return Response(read.data)

    @extend_schema(responses={204: None})
    def destroy(self, request: Request, pk: str | None = None) -> Response:
        """Delete via DeleteOutfitAction (cascades slots)."""
        from actions.definitions.outfits import DeleteOutfitAction  # noqa: PLC0415

        outfit_pk = _parse_int_param(pk)
        if outfit_pk is None:
            raise NotFound
        try:
            outfit = Outfit.objects.select_related("character_sheet").get(pk=outfit_pk)
        except Outfit.DoesNotExist as exc:
            raise NotFound from exc
        self.check_object_permissions(request, outfit)
        actor = outfit.character_sheet.character
        action_result = DeleteOutfitAction().run(actor=actor, outfit=outfit)
        if not action_result.success:
            # See OutfitViewSet.create's note above: field-specific errors collapse to
            # non_field_errors since ActionResult carries only a message.
            raise serializers.ValidationError({"non_field_errors": [action_result.message]})
        return Response(status=204)


@extend_schema(tags=["items"])
class OutfitSlotViewSet(viewsets.ViewSet):
    """ViewSet for OutfitSlot create/list/delete.

    Item-first / outfit-scoped shape:

    - ``outfit`` query parameter is REQUIRED for list.
    - List walks ``outfit.cached_outfit_slots`` (prefetch target).
    - Write actions delegate to existing serializers + services.
    """

    http_method_names = ["get", "post", "delete", "head", "options"]
    permission_classes = [OutfitSlotWritePermission]
    serializer_class = OutfitSlotReadSerializer

    @extend_schema(
        responses=_paginated_response(OutfitSlotReadSerializer),
        parameters=[
            OpenApiParameter(
                name="outfit",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Outfit pk whose slots to list.",
            ),
        ],
    )
    def list(self, request: Request) -> Response:
        """Return OutfitSlot rows for ``?outfit=<pk>``."""
        user = cast(AccountDB, request.user)
        # noqa: USE_FILTERSET
        outfit_pk = _parse_int_param(request.query_params.get("outfit"))  # noqa: USE_FILTERSET
        if outfit_pk is None:
            raise serializers.ValidationError({"outfit": REQUIRED_QUERY_PARAM_MESSAGE})
        try:
            outfit = (
                Outfit.objects.select_related("character_sheet")
                .prefetch_related(
                    Prefetch(
                        "slots",
                        queryset=OutfitSlot.objects.select_related(
                            "item_instance",
                            "item_instance__template",
                            "item_instance__quality_tier",
                            "item_instance__currency_instrument",
                        ),
                        to_attr="cached_outfit_slots",
                    ),
                )
                .get(pk=outfit_pk)
            )
        except Outfit.DoesNotExist as exc:
            raise NotFound from exc

        if not user.is_staff and not _user_plays_pk(user, outfit.character_sheet_id):
            raise NotFound

        rows = list(outfit.cached_outfit_slots)
        paginator = ItemTemplatePagination()
        page = paginator.paginate_queryset(rows, request, view=self)  # ty: ignore[invalid-argument-type]
        serializer = OutfitSlotReadSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(responses=OutfitSlotReadSerializer)
    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        """Return a single OutfitSlot if the requester may view it."""
        user = cast(AccountDB, request.user)
        slot_pk = _parse_int_param(pk)
        if slot_pk is None:
            raise NotFound
        try:
            slot = OutfitSlot.objects.select_related(
                "outfit",
                "outfit__character_sheet",
                "item_instance",
                "item_instance__template",
                "item_instance__quality_tier",
                "item_instance__currency_instrument",
            ).get(pk=slot_pk)
        except OutfitSlot.DoesNotExist as exc:
            raise NotFound from exc

        if not user.is_staff and not _user_plays_pk(user, slot.outfit.character_sheet_id):
            raise NotFound

        serializer = OutfitSlotReadSerializer(slot)
        return Response(serializer.data)

    @extend_schema(request=OutfitSlotWriteSerializer, responses=OutfitSlotReadSerializer)
    def create(self, request: Request) -> Response:
        """Create an OutfitSlot via AddOutfitSlotAction (validates via the existing serializer).

        Cache invalidation lives inside ``add_outfit_slot`` (called by the
        Action), so no manual invalidation is needed here.
        """
        from actions.definitions.outfits import AddOutfitSlotAction  # noqa: PLC0415

        serializer = OutfitSlotWriteSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        outfit = serializer.validated_data["outfit"]
        item_instance = serializer.validated_data["item_instance"]
        body_region = serializer.validated_data["body_region"]
        equipment_layer = serializer.validated_data["equipment_layer"]
        actor = outfit.character_sheet.character
        action_result = AddOutfitSlotAction().run(
            actor=actor,
            outfit=outfit,
            item_instance=item_instance,
            body_region=body_region,
            equipment_layer=equipment_layer,
        )
        if not action_result.success:
            # Field-specific errors (e.g. "item_instance") collapse to non_field_errors
            # here — AddOutfitSlotAction's ActionResult carries only a message (#1866).
            raise serializers.ValidationError({"non_field_errors": [action_result.message]})
        read = OutfitSlotReadSerializer(action_result.data["slot"])
        return Response(read.data, status=201)

    @extend_schema(responses={204: None})
    def destroy(self, request: Request, pk: str | None = None) -> Response:
        """Delete via RemoveOutfitSlotAction (idempotent).

        Cache invalidation lives inside ``remove_outfit_slot``.
        """
        from actions.definitions.outfits import RemoveOutfitSlotAction  # noqa: PLC0415

        slot_pk = _parse_int_param(pk)
        if slot_pk is None:
            raise NotFound
        try:
            slot = OutfitSlot.objects.select_related("outfit", "outfit__character_sheet").get(
                pk=slot_pk
            )
        except OutfitSlot.DoesNotExist as exc:
            raise NotFound from exc
        self.check_object_permissions(request, slot)
        actor = slot.outfit.character_sheet.character
        action_result = RemoveOutfitSlotAction().run(
            actor=actor,
            outfit=slot.outfit,
            body_region=slot.body_region,
            equipment_layer=slot.equipment_layer,
        )
        if not action_result.success:
            # See OutfitSlotViewSet.create's note above: field-specific errors collapse
            # to non_field_errors since ActionResult carries only a message.
            raise serializers.ValidationError({"non_field_errors": [action_result.message]})
        return Response(status=204)


def _parse_int_param(value: object) -> int | None:
    """Parse ``value`` as a positive int, returning None on failure."""
    if value is None:
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _fetch_objectdb(raw_pk: object) -> ObjectDB | None:
    """Parse ``raw_pk`` and fetch the matching ObjectDB, or None on miss."""
    pk = _parse_int_param(raw_pk)
    if pk is None:
        return None
    try:
        return ObjectDB.objects.get(pk=pk)
    except ObjectDB.DoesNotExist:
        return None


def _fetch_owned_observer(request: Request, user: AccountDB) -> ObjectDB | None:
    """Fetch the ``?observer=<pk>`` ObjectDB iff it belongs to ``user``.

    The visible-worn endpoints are computed views (not queryset-backed),
    so the FilterSet pattern doesn't apply — the ``observer`` parameter
    is a permission-context input, not a filter on a queryset.
    """
    # noqa: USE_FILTERSET
    observer = _fetch_objectdb(request.query_params.get("observer"))  # noqa: USE_FILTERSET
    if observer is None:
        return None
    if observer.db_account_id != user.id:
        return None
    return observer


@dataclass(frozen=True)
class _VisibleWornContext:
    """Resolved (target, observer) pair for the visible-worn list endpoint.

    ``observer`` may be the target itself (self-look bypass), an ObjectDB
    in the same room, or the staff user (full bypass).
    """

    target: ObjectDB
    observer: object


def _is_concealed_for_observer(item: ItemInstance, wearing_character: ObjectDB) -> bool:
    """Whether ``item`` is concealed by a higher covering layer at the
    same body region.

    Walks the cached ``equipped_items`` handler — no queries when the
    handler is warm. Returns True if the item is not equipped (so it
    should not be visible to others).
    """
    target_row = None
    for row in wearing_character.equipped_items:
        if row.item_instance.pk == item.pk:
            target_row = row
            break
    if target_row is None:
        return True  # not equipped → not visible to others

    target_region = target_row.body_region
    target_rank = LAYER_RANK.get(target_row.equipment_layer, 99)

    for row in wearing_character.equipped_items:
        if row.pk == target_row.pk:
            continue
        if row.body_region != target_region:
            continue
        other_rank = LAYER_RANK.get(row.equipment_layer, 99)
        if other_rank <= target_rank:
            continue
        for slot in row.item_instance.template.cached_slots:
            if (
                slot.body_region == target_region
                and slot.equipment_layer == row.equipment_layer
                and slot.covers_lower_layers
            ):
                return True
    return False


class VisibleWornItemViewSet(viewsets.ViewSet):
    """List visible worn items for a character.

    Item-first permission shape:

    - ``character`` query parameter selects the target being looked at.
    - ``observer`` query parameter selects which of the requester's
      characters is doing the looking (required for non-staff).

    Permission rules:

    - Staff: full visibility (no observer required).
    - Non-staff: observer must belong to the requester, and either match
      the target (self-look) or share a room with the target.

    Out-of-scope requests return ``[]`` (200) — never 403/404 — to avoid
    leaking presence information about characters in rooms the observer
    can't see.
    """

    permission_classes = [PlayerOrStaffPermission]
    filter_backends = [DjangoFilterBackend]
    filterset_class = VisibleWornItemFilter

    def list(self, request: Request) -> Response:
        """Return the slim visible-worn list for ``?character=<pk>``."""
        user = cast(AccountDB, request.user)
        observer = self._resolve_observer(request, user)
        if observer is None:
            return Response([])

        items = visible_worn_items_for(observer.target, observer=observer.observer)
        serializer = VisibleWornItemSerializer(items, many=True)
        return Response(serializer.data)

    def _resolve_observer(self, request: Request, user: AccountDB) -> _VisibleWornContext | None:
        """Resolve target + observer for the request, or None if out of scope.

        Computed (non-queryset) view — character/observer parameters are
        identity inputs, not queryset filters, so the FilterSet pattern
        doesn't apply.
        """
        # noqa: USE_FILTERSET
        target = _fetch_objectdb(request.query_params.get("character"))  # noqa: USE_FILTERSET
        if target is None:
            return None

        if user.is_staff:
            # Staff bypass: no observer needed, layer hiding bypassed.
            return _VisibleWornContext(target=target, observer=user)

        observer_obj = _fetch_owned_observer(request, user)
        if observer_obj is None:
            return None

        if observer_obj.pk == target.pk:
            # Self-look: pass the target itself so the service's
            # ``observer is character`` bypass fires.
            return _VisibleWornContext(target=target, observer=target)

        # Must share a room.
        if observer_obj.db_location_id != target.db_location_id:
            return None
        return _VisibleWornContext(target=target, observer=observer_obj)


class VisibleItemDetailViewSet(viewsets.ViewSet):
    """Read-only detail for a single visibly worn item.

    Item-first permission shape: fetch the item directly, then check
    whether the requester is allowed to view it.

    The wearing character is derived from ``item.game_object.location``
    (equipped items have their location set to the wearing character) —
    no RosterEntry walk, no roster queries.

    Permission rules:

    - Staff: 200 (bypass).
    - Non-staff with ``?observer=<own_char_pk>``:
      - Observer must belong to the requester.
      - Self-look (observer == wearing character): 200 even for concealed
        items.
      - Same-room: 200 if the item is not concealed by a higher covering
        layer; 404 if concealed.
      - Different room or no observer: 404.
    """

    permission_classes = [PlayerOrStaffPermission]

    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        """Return the ItemInstance for ``pk`` if the requester may view it."""
        item_pk = _parse_int_param(pk)
        if item_pk is None:
            raise NotFound

        user = cast(AccountDB, request.user)

        # Fetch the item with the same prefetch chain the read serializer
        # uses, so serialization runs zero extra queries. Identity map will
        # share these instances with any other code path that already
        # loaded them.
        try:
            item = (
                ItemInstance.objects.select_related(
                    "template",
                    "quality_tier",
                    "game_object",
                    "image",
                    "template__image",
                    "currency_instrument",
                )
                .prefetch_related(
                    Prefetch(
                        "item_facets",
                        queryset=ItemFacet.objects.select_related(
                            "facet",
                            "attachment_quality_tier",
                        ),
                        to_attr="cached_item_facets",
                    ),
                )
                .get(pk=item_pk)
            )
        except ItemInstance.DoesNotExist as exc:
            raise NotFound from exc

        if not self._user_can_view(user, item, request):
            raise NotFound  # don't leak existence

        # #1909: surface can_steal from the observer's perspective — the
        # only place this serializer is used to look at somebody else's
        # item. Re-fetches ``?observer=`` (already validated above by
        # ``_user_can_view``); a single extra pk lookup on a detail
        # endpoint, not worth threading through the permission check.
        serializer = ItemInstanceReadSerializer(
            item, context={"viewer_sheet": self._resolve_viewer_sheet(user, request)}
        )
        return Response(serializer.data)

    def _resolve_viewer_sheet(self, user: AccountDB, request: Request) -> CharacterSheet | None:
        """The observer's ``CharacterSheet`` for ``can_steal``, or None (#1909).

        None for staff (no observer concept here) and for requests with no
        owned observer — ``can_steal`` then defaults to False.
        """
        if user.is_staff:
            return None
        observer = _fetch_owned_observer(request, user)
        if observer is None:
            return None
        return observer.character_sheet

    def _user_can_view(self, user: AccountDB, item: ItemInstance, request: Request) -> bool:
        """Permission check for ``item`` against ``user`` and the observer."""
        if user.is_staff:
            return True

        observer = _fetch_owned_observer(request, user)
        if observer is None:
            return False

        # Wearing character is derived from item location — equipped
        # items have their game_object's location set to the wearer.
        wearing_character = item.game_object.db_location
        if wearing_character is None:
            return False

        # Self-look: bypass hiding.
        if observer.pk == wearing_character.pk:
            return True

        # Same-room check.
        if observer.db_location_id != wearing_character.db_location_id:
            return False

        # Visible (not concealed by a covering layer)?
        return not _is_concealed_for_observer(item, wearing_character)


# =============================================================================
# Fashion presentation + peer judging (Outfits Phase C, #514)
# =============================================================================
#
# Modelled on ``PoseEndorsementViewSet`` / ``SceneEntryEndorsementViewSet`` in
# ``world/magic/views.py``: the acting CharacterSheet (presenter / judge) is
# resolved from the requesting account's active tenure via
# ``_resolve_actor_sheet`` — it is never accepted from the client.


class FashionPresentationViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    GenericViewSet,
):
    """Present an outfit + list presentations (#514).

    POST /api/items/fashion-presentations/ — record the requesting account's
    acting character presenting an outfit at an event.
    GET  /api/items/fashion-presentations/?event=<id> — list presentations
    (filterable by event) so the UI can show who is presenting there to judge.
    GET  /api/items/fashion-presentations/<pk>/ — retrieve one presentation.
    """

    queryset = FashionPresentation.objects.select_related(
        "event",
        "presenter",
        "outfit",
        "perceiving_society",
    ).order_by("-created_at")
    serializer_class = FashionPresentationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = ItemTemplatePagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = FashionPresentationFilter

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Record the requesting account's acting character presenting an outfit at an event.

        Body: ``event`` (required) + optional ``outfit`` PKs. Returns the created
        presentation (201), or 400 when the event has no host society / other rule failure.
        """
        # Converged onto the registered PresentOutfitAction so telnet and web share one
        # seam (ADR-0001, #1508): the serializer validates input + serializes the result,
        # but the Action — not the serializer — orchestrates the presentation (and emits the
        # present-outfit events + scene message the web path previously skipped). The
        # presenter is resolved server-side from the requesting account, never the client.
        from actions.definitions.fashion import PresentOutfitAction  # noqa: PLC0415

        in_serializer = self.get_serializer(data=request.data)
        in_serializer.is_valid(raise_exception=True)
        event = in_serializer.validated_data["event"]
        outfit = in_serializer.validated_data.get("outfit")

        presenter = _resolve_actor_sheet(self.request, body_key="presenter_sheet_id")
        result = PresentOutfitAction().run(
            actor=presenter.character,
            event_id=event.pk,
            outfit_id=outfit.pk if outfit is not None else None,
        )
        if not result.success:
            raise serializers.ValidationError({"detail": result.message})

        presentation = result.data["presentation"]
        out_serializer = self.get_serializer(presentation)
        headers = self.get_success_headers(out_serializer.data)
        return Response(out_serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class FashionJudgementViewSet(
    mixins.CreateModelMixin,
    GenericViewSet,
):
    """Judge a fashion presentation (#514).

    POST /api/items/fashion-judgements/ — the requesting account's acting
    character endorses a presentation; the created
    ``PresentationEndorsement`` is returned. Self-judging, alt-judging, and
    duplicate judging are rejected with HTTP 400 (friendly message).
    """

    pagination_class = None  # 2026-07 audit: opt out of default paginator (ADR-0138)

    queryset = FashionPresentation.objects.none()
    serializer_class = FashionJudgementSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Validate, resolve the judge sheet, and return the endorsement."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        judge = _resolve_actor_sheet(request, body_key="judge_sheet_id")
        endorsement = serializer.save(judge=judge)
        read = PresentationEndorsementSerializer(endorsement)
        return Response(read.data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["items"])
class ItemStyleCraftViewSet(viewsets.ViewSet):
    """ViewSet for style crafting: POST rolls the check and attaches a Style to an item.

    Mirrors ``ItemFacetViewSet.create`` — validates ``item_instance`` + ``style``
    ownership, dispatches through ``AttachStyleAction``, and returns 201 on
    attach or 200 on a failed roll.
    """

    http_method_names = ["get", "post", "head", "options"]
    permission_classes = [ItemStyleWritePermission]
    serializer_class = StyleCraftResultSerializer

    @extend_schema(request=ItemStyleWriteSerializer, responses=StyleCraftResultSerializer)
    def create(self, request: Request) -> Response:
        """Roll the crafting check and (on success) attach the style, via the Action."""
        from actions.definitions.crafting import AttachStyleAction  # noqa: PLC0415

        serializer = ItemStyleWriteSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        item_instance = serializer.validated_data["item_instance"]
        style = serializer.validated_data["style"]
        actor = item_instance.holder_character_sheet.character
        action_result = AttachStyleAction().run(
            actor=actor, item_instance=item_instance, style=style
        )
        if not action_result.success:
            raise serializers.ValidationError({"non_field_errors": [action_result.message]})
        result = action_result.data["result"]
        status_code = 201 if result.attached else 200
        return Response(StyleCraftResultSerializer(result).data, status=status_code)

    @extend_schema(
        responses=CraftingQuoteSerializer,
        parameters=[
            OpenApiParameter(
                name="item_instance",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=True,
                description="ItemInstance pk to quote the crafting cost for.",
            ),
            OpenApiParameter(
                name="style",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Style pk that would be attached.",
            ),
        ],
    )
    @action(detail=False, methods=[HTTPMethod.GET], url_path="quote")
    def quote(self, request: Request) -> Response:
        """Return a read-only cost+quality quote for attaching a style (no mutation)."""
        from world.items.crafting.constants import CraftingRecipeKind  # noqa: PLC0415
        from world.items.crafting.services import build_crafting_quote  # noqa: PLC0415
        from world.items.models import Style  # noqa: PLC0415

        user = cast(AccountDB, request.user)
        instance_pk = _parse_int_param(request.query_params.get("item_instance"))  # noqa: USE_FILTERSET
        style_pk = _parse_int_param(request.query_params.get("style"))  # noqa: USE_FILTERSET
        if instance_pk is None:
            raise serializers.ValidationError({"item_instance": REQUIRED_QUERY_PARAM_MESSAGE})
        if style_pk is None:
            raise serializers.ValidationError({"style": REQUIRED_QUERY_PARAM_MESSAGE})
        try:
            item_instance = ItemInstance.objects.select_related(
                "holder_character_sheet__character"
            ).get(pk=instance_pk)
        except ItemInstance.DoesNotExist as exc:
            raise NotFound from exc
        if not user.is_staff and not _user_holds_item(user, item_instance):
            raise NotFound
        try:
            style = Style.objects.get(pk=style_pk)
        except Style.DoesNotExist as exc:
            raise NotFound from exc
        crafter_character = item_instance.holder_character_sheet.character
        crafter_character_sheet = item_instance.holder_character_sheet
        try:
            quote = build_crafting_quote(
                kind=CraftingRecipeKind.STYLE_ATTACH,
                crafter_character=crafter_character,
                crafter_character_sheet=crafter_character_sheet,
                target=style,
            )
        except CraftingNotConfigured as exc:
            raise serializers.ValidationError({"non_field_errors": [exc.user_message]}) from exc
        return Response(CraftingQuoteSerializer(quote).data)


@extend_schema(tags=["items"])
class ItemCreateCraftViewSet(viewsets.ViewSet):
    """ViewSet for item-creation crafting: browse recipes, quote, and mint (#2211/#2240).

    - GET  /api/items/crafting/create/recipes/ — what this character can craft.
    - GET  /api/items/crafting/create/quote/   — cost/quality quote for one template.
    - POST /api/items/crafting/create/          — roll the check and mint the item.
    """

    http_method_names = ["get", "post", "head", "options"]
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=CraftableTemplateSerializer(many=True))
    @action(detail=False, methods=[HTTPMethod.GET], url_path="recipes")
    def recipes(self, request: Request) -> Response:
        """List the item-creation recipes this character can craft (#2240, #2242).

        Open recipes are always listed; a ``requires_knowledge`` recipe appears
        only when the acting character has learned it (#2242).
        """
        from django.db.models import Q  # noqa: PLC0415

        from world.items.crafting.constants import CraftingRecipeKind  # noqa: PLC0415
        from world.items.crafting.models import CraftingRecipe  # noqa: PLC0415

        actor_sheet = _resolve_actor_sheet(request, "crafter_sheet_id", from_query=True)
        recipes = (
            CraftingRecipe.objects.filter(
                kind=CraftingRecipeKind.ITEM_CREATE,
                output_item_template__is_active=True,
                output_item_template__is_craftable=True,
            )
            .filter(Q(requires_knowledge=False) | Q(known_by__character_sheet=actor_sheet))
            .select_related("output_item_template")
            .distinct()
            .order_by("output_item_template__name")
        )
        templates = [r.output_item_template for r in recipes]
        return Response(CraftableTemplateSerializer(templates, many=True).data)

    @extend_schema(responses=CraftingQuoteSerializer)
    @action(detail=False, methods=[HTTPMethod.GET], url_path="quote")
    def quote(self, request: Request) -> Response:
        """Return a read-only cost+quality quote for minting a template (no mutation)."""
        from world.items.crafting.constants import CraftingRecipeKind  # noqa: PLC0415
        from world.items.crafting.services import build_crafting_quote  # noqa: PLC0415

        template_pk = _parse_int_param(request.query_params.get("template"))  # noqa: USE_FILTERSET
        if template_pk is None:
            raise serializers.ValidationError({"template": REQUIRED_QUERY_PARAM_MESSAGE})
        try:
            template = ItemTemplate.objects.get(pk=template_pk, is_active=True)
        except ItemTemplate.DoesNotExist as exc:
            raise NotFound from exc
        actor_sheet = _resolve_actor_sheet(request, "crafter_sheet_id", from_query=True)
        try:
            quote = build_crafting_quote(
                kind=CraftingRecipeKind.ITEM_CREATE,
                crafter_character=actor_sheet.character,
                crafter_character_sheet=actor_sheet,
                output_template=template,
            )
        except CraftingNotConfigured as exc:
            raise serializers.ValidationError({"non_field_errors": [exc.user_message]}) from exc
        return Response(CraftingQuoteSerializer(quote).data)

    def create(self, request: Request) -> Response:
        """Roll the crafting check and (on success) mint a new ItemInstance."""
        from actions.definitions.crafting import CreateItemAction  # noqa: PLC0415

        template_pk = request.data.get("template")
        custom_name = request.data.get("custom_name", "")
        custom_description = request.data.get("custom_description", "")
        if not template_pk:
            raise serializers.ValidationError({"template": "This field is required."})
        try:
            template = ItemTemplate.objects.get(pk=template_pk, is_active=True)
        except ItemTemplate.DoesNotExist as exc:
            raise NotFound from exc
        actor_sheet = _resolve_actor_sheet(request, body_key="crafter_sheet_id")
        action_result = CreateItemAction().run(
            actor=actor_sheet.character,
            output_template=template,
            custom_name=custom_name,
            custom_description=custom_description,
        )
        if not action_result.success:
            raise serializers.ValidationError({"non_field_errors": [action_result.message]})
        result = action_result.data["result"]
        status_code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
        return Response(
            {
                "created": result.created,
                "item_instance_id": result.item_instance.pk if result.item_instance else None,
                "quality_tier": str(result.quality_tier) if result.quality_tier else None,
                "consequence_label": result.consequence_label,
            },
            status=status_code,
        )


class ReclamationClaimViewSet(viewsets.ViewSet):
    """Theft reclamation (#2368): the claimant's own claims + trace + routes.

    Self-only: scoped to the requesting account's characters' sheets. The
    holder is never notified a claim exists.
    """

    permission_classes = [IsAuthenticated]

    def _own_sheets(self, request: Request) -> list:
        from world.roster.models import RosterEntry  # noqa: PLC0415

        account = cast(AccountDB, request.user)
        return [entry.character_sheet for entry in RosterEntry.objects.for_account(account)]

    def _own_claim(self, request: Request, pk: object) -> ReclamationClaim | None:
        return ReclamationClaim.objects.filter(
            pk=pk, claimant_sheet__in=self._own_sheets(request)
        ).first()

    @staticmethod
    def _claim_payload(claim: ReclamationClaim) -> dict:
        from world.items.services.reclamation import trace_complete  # noqa: PLC0415

        return {
            "id": claim.pk,
            "item_name": claim.item_instance.display_name,
            "status": claim.status,
            "origin": claim.origin,
            "trace_position": claim.trace_position,
            "trace_complete": trace_complete(claim),
            "steps": [
                {"position": s.position, "text": s.revealed_text} for s in claim.trace_steps.all()
            ],
        }

    def list(self, request: Request) -> Response:
        claims = ReclamationClaim.objects.filter(
            claimant_sheet__in=self._own_sheets(request)
        ).select_related("item_instance")
        return Response({"claims": [self._claim_payload(c) for c in claims]})

    @action(detail=False, methods=[HTTPMethod.GET], url_path="claimable")
    def claimable(self, request: Request) -> Response:
        """Items stolen from the viewer's characters with no open claim yet (#2368).

        The filing seam: the victim discovers the theft here and mints the claim.
        Self-scoped and tiny (a player's own unresolved thefts), so the per-item
        provenance check stays a simple loop.
        """
        from world.items.constants import ClaimStatus, OwnershipEventType  # noqa: PLC0415
        from world.items.models import OwnershipEvent  # noqa: PLC0415
        from world.items.services.provenance import stolen_victim  # noqa: PLC0415

        sheets = self._own_sheets(request)
        candidate_items = {
            event.item_instance
            for event in OwnershipEvent.objects.filter(
                event_type=OwnershipEventType.STOLEN,
                from_character_sheet__in=sheets,
            ).select_related("item_instance")
        }
        claimed_ids = set(
            ReclamationClaim.objects.filter(
                claimant_sheet__in=sheets, status=ClaimStatus.OPEN
            ).values_list("item_instance_id", flat=True)
        )
        rows = [
            {"item": item.pk, "item_name": item.display_name}
            for item in candidate_items
            if item.pk not in claimed_ids and stolen_victim(item) in sheets
        ]
        return Response({"claimable": rows})

    @action(detail=False, methods=[HTTPMethod.POST], url_path="file")
    def file_claim(self, request: Request) -> Response:
        from world.items.models import ItemInstance  # noqa: PLC0415
        from world.items.services.reclamation import (  # noqa: PLC0415
            ReclamationError,
            file_theft_claim,
        )

        raw = request.data.get("item")
        item = (
            ItemInstance.objects.filter(pk=int(raw)).first()
            if raw is not None and str(raw).isdigit()
            else None
        )
        if item is None:
            return Response({"detail": "Unknown item."}, status=400)
        for sheet in self._own_sheets(request):
            try:
                claim = file_theft_claim(sheet, item)
            except ReclamationError:
                continue
            return Response(self._claim_payload(claim), status=201)
        return Response({"detail": "You have no standing claim on that item."}, status=400)

    @action(detail=True, methods=[HTTPMethod.POST], url_path="advance")
    def advance(self, request: Request, pk: object = None) -> Response:
        from world.items.services.reclamation import (  # noqa: PLC0415
            ReclamationError,
            advance_trace,
        )

        claim = self._own_claim(request, pk)
        if claim is None:
            return Response({"detail": _UNKNOWN_CLAIM_MSG}, status=400)
        try:
            outcome = advance_trace(claim)
        except ReclamationError as exc:
            return Response({"detail": exc.user_message}, status=400)
        claim.refresh_from_db()
        return Response({**outcome, "claim": self._claim_payload(claim)})

    @action(detail=True, methods=[HTTPMethod.POST], url_path="report")
    def report(self, request: Request, pk: object = None) -> Response:
        from world.items.services.reclamation import (  # noqa: PLC0415
            ReclamationError,
            file_reclamation_accusation,
        )

        claim = self._own_claim(request, pk)
        if claim is None:
            return Response({"detail": _UNKNOWN_CLAIM_MSG}, status=400)
        try:
            minted = file_reclamation_accusation(claim)
        except ReclamationError as exc:
            return Response({"detail": exc.user_message}, status=400)
        return Response({"reported": True, "heat_minted": minted})

    @action(detail=True, methods=[HTTPMethod.POST], url_path="take-back")
    def take_back(self, request: Request, pk: object = None) -> Response:
        from world.items.services.reclamation import (  # noqa: PLC0415
            ReclamationError,
            record_steal_back,
        )

        claim = self._own_claim(request, pk)
        if claim is None:
            return Response({"detail": _UNKNOWN_CLAIM_MSG}, status=400)
        try:
            record_steal_back(claim, claim.original_claimant_sheet)
        except ReclamationError as exc:
            return Response({"detail": exc.user_message}, status=400)
        claim.refresh_from_db()
        return Response(self._claim_payload(claim))
