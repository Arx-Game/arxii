"""API ViewSets for items."""

from dataclasses import dataclass
from typing import cast

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
from rest_framework import serializers, viewsets
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core_management.permissions import PlayerOrStaffPermission
from flows.service_functions.outfits import delete_outfit, remove_outfit_slot
from world.character_sheets.models import CharacterSheet
from world.items.filters import (
    InteractionTypeFilter,
    ItemTemplateFilter,
    QualityTierFilter,
    VisibleWornItemFilter,
)
from world.items.models import (
    EquippedItem,
    InteractionType,
    ItemFacet,
    ItemInstance,
    ItemTemplate,
    Outfit,
    OutfitSlot,
    QualityTier,
    TemplateInteraction,
    TemplateSlot,
)
from world.items.serializers import (
    EquippedItemReadSerializer,
    InteractionTypeSerializer,
    ItemFacetReadSerializer,
    ItemFacetWriteSerializer,
    ItemInstanceReadSerializer,
    ItemTemplateDetailSerializer,
    ItemTemplateListSerializer,
    OutfitReadSerializer,
    OutfitRenameSerializer,
    OutfitSlotReadSerializer,
    OutfitSlotWriteSerializer,
    OutfitWriteSerializer,
    QualityTierSerializer,
    VisibleWornItemSerializer,
)
from world.items.services.appearance import LAYER_RANK, visible_worn_items_for
from world.items.services.facets import remove_facet_from_item
from world.roster.models import RosterEntry


def _user_plays_pk(user: AccountDB, pk: int) -> bool:
    """True if ``user`` has an active roster tenure on the character_sheet at ``pk``.

    Character pk equals CharacterSheet pk by construction
    (``CharacterSheet.character = OneToOneField(primary_key=True)``), so this
    helper covers both "does the user play this Character?" and "does the
    user play this CharacterSheet?" without needing two helpers.
    """
    return RosterEntry.objects.for_account(user).filter(character_sheet_id=pk).exists()


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
            return ItemInstance.objects.filter(pk=instance_pk, owner=request.user).exists()
        return True  # DELETE checked at object level

    def has_object_permission_for_player(
        self, request: Request, view: APIView, obj: ItemFacet
    ) -> bool:
        return obj.item_instance.owner_id == request.user.pk


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
        # noqa: USE_FILTERSET — required scope param for item-first endpoint
        instance_pk = _parse_int_param(request.query_params.get("item_instance"))  # noqa: USE_FILTERSET
        if instance_pk is None:
            raise serializers.ValidationError(
                {"item_instance": "This query parameter is required."}
            )
        try:
            item = (
                ItemInstance.objects.select_related("owner")
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

        if not user.is_staff and item.owner_id != user.pk:
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
                "item_instance__owner",
                "facet",
                "attachment_quality_tier",
                "applied_by_account",
            ).get(pk=row_pk)
        except ItemFacet.DoesNotExist as exc:
            raise NotFound from exc

        if not user.is_staff and row.item_instance.owner_id != user.pk:
            raise NotFound

        serializer = ItemFacetReadSerializer(row)
        return Response(serializer.data)

    @extend_schema(request=ItemFacetWriteSerializer, responses=ItemFacetReadSerializer)
    def create(self, request: Request) -> Response:
        """Attach a facet via the serializer (which calls the service)."""
        serializer = ItemFacetWriteSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        row = serializer.save()
        read = ItemFacetReadSerializer(row)
        return Response(read.data, status=201)

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
        remove_facet_from_item(item_facet=row)
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
        # noqa: USE_FILTERSET — required scope param for item-first endpoint
        character_pk = _parse_int_param(request.query_params.get("character"))  # noqa: USE_FILTERSET
        if character_pk is None:
            raise serializers.ValidationError({"character": "This query parameter is required."})
        try:
            character = ObjectDB.objects.get(pk=character_pk)
        except ObjectDB.DoesNotExist as exc:
            raise NotFound from exc

        if not user.is_staff and not _user_plays_pk(user, character.pk):
            raise NotFound

        rows = list(character.carried_items)
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
                ItemInstance.objects.select_related(
                    "template",
                    "quality_tier",
                    "game_object",
                    "image",
                    "template__image",
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

        serializer = ItemInstanceReadSerializer(item)
        return Response(serializer.data)


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
        # noqa: USE_FILTERSET — required scope param for item-first endpoint
        character_pk = _parse_int_param(request.query_params.get("character"))  # noqa: USE_FILTERSET
        if character_pk is None:
            raise serializers.ValidationError({"character": "This query parameter is required."})
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
        # noqa: USE_FILTERSET — required scope param for item-first endpoint
        sheet_pk = _parse_int_param(request.query_params.get("character_sheet"))  # noqa: USE_FILTERSET
        if sheet_pk is None:
            raise serializers.ValidationError(
                {"character_sheet": "This query parameter is required."}
            )
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
        """Create an Outfit via the existing write serializer (calls save_outfit)."""
        serializer = OutfitWriteSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        outfit = serializer.save()
        read = OutfitReadSerializer(outfit)
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
        outfit_pk = _parse_int_param(pk)
        if outfit_pk is None:
            raise NotFound
        try:
            outfit = Outfit.objects.select_related("character_sheet").get(pk=outfit_pk)
        except Outfit.DoesNotExist as exc:
            raise NotFound from exc
        self.check_object_permissions(request, outfit)
        serializer = OutfitRenameSerializer(
            outfit,
            data=request.data,
            partial=partial,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        outfit = serializer.save()
        # Invalidate the sheet's outfits handler so the rename shows next read.
        outfit.character_sheet.saved_outfits.invalidate()
        read = OutfitReadSerializer(outfit)
        return Response(read.data)

    @extend_schema(responses={204: None})
    def destroy(self, request: Request, pk: str | None = None) -> Response:
        """Delete via the delete_outfit service (cascades slots)."""
        outfit_pk = _parse_int_param(pk)
        if outfit_pk is None:
            raise NotFound
        try:
            outfit = Outfit.objects.select_related("character_sheet").get(pk=outfit_pk)
        except Outfit.DoesNotExist as exc:
            raise NotFound from exc
        self.check_object_permissions(request, outfit)
        sheet = outfit.character_sheet
        delete_outfit(outfit)
        sheet.saved_outfits.invalidate()
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
        # noqa: USE_FILTERSET — required scope param for item-first endpoint
        outfit_pk = _parse_int_param(request.query_params.get("outfit"))  # noqa: USE_FILTERSET
        if outfit_pk is None:
            raise serializers.ValidationError({"outfit": "This query parameter is required."})
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
            ).get(pk=slot_pk)
        except OutfitSlot.DoesNotExist as exc:
            raise NotFound from exc

        if not user.is_staff and not _user_plays_pk(user, slot.outfit.character_sheet_id):
            raise NotFound

        serializer = OutfitSlotReadSerializer(slot)
        return Response(serializer.data)

    @extend_schema(request=OutfitSlotWriteSerializer, responses=OutfitSlotReadSerializer)
    def create(self, request: Request) -> Response:
        """Create an OutfitSlot via the existing write serializer.

        Cache invalidation lives inside ``add_outfit_slot`` (called by the
        serializer's ``create``), so no manual invalidation is needed here.
        """
        serializer = OutfitSlotWriteSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        slot = serializer.save()
        read = OutfitSlotReadSerializer(slot)
        return Response(read.data, status=201)

    @extend_schema(responses={204: None})
    def destroy(self, request: Request, pk: str | None = None) -> Response:
        """Delete via remove_outfit_slot (idempotent).

        Cache invalidation lives inside ``remove_outfit_slot``.
        """
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
        remove_outfit_slot(
            outfit=slot.outfit,
            body_region=slot.body_region,
            equipment_layer=slot.equipment_layer,
        )
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
    # noqa: USE_FILTERSET — permission-context param on a computed (non-queryset) view
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
        # noqa: USE_FILTERSET — computed view, not queryset filtering
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

        serializer = ItemInstanceReadSerializer(item)
        return Response(serializer.data)

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
