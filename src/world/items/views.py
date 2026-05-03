"""API ViewSets for items."""

from dataclasses import dataclass
from typing import cast

from django.db.models import Prefetch, QuerySet
from django_filters.rest_framework import DjangoFilterBackend
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
    EquippedItemFilter,
    InteractionTypeFilter,
    ItemFacetFilter,
    ItemInstanceFilter,
    ItemTemplateFilter,
    OutfitFilter,
    OutfitSlotFilter,
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
    OutfitSlotReadSerializer,
    OutfitSlotWriteSerializer,
    OutfitWriteSerializer,
    QualityTierSerializer,
    VisibleWornItemSerializer,
)
from world.items.services.appearance import LAYER_RANK, visible_worn_items_for
from world.items.services.facets import remove_facet_from_item
from world.roster.models import RosterEntry


def _account_currently_plays(user: AccountDB, sheet: CharacterSheet) -> bool:
    """True if ``user`` has an active roster tenure on ``sheet``."""
    return RosterEntry.objects.for_account(user).filter(character_sheet=sheet).exists()


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


class ItemFacetViewSet(viewsets.ModelViewSet):
    """ViewSet for ItemFacet attach/list/delete."""

    http_method_names = ["get", "post", "delete", "head", "options"]
    permission_classes = [ItemFacetWritePermission]
    pagination_class = ItemTemplatePagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = ItemFacetFilter
    queryset = ItemFacet.objects.select_related(
        "item_instance",
        "facet",
        "applied_by_account",
        "attachment_quality_tier",
    ).order_by("-applied_at")

    def get_serializer_class(self) -> type[serializers.ModelSerializer]:
        """Use write serializer for create, read serializer otherwise."""
        if self.action == "create":
            return ItemFacetWriteSerializer
        return ItemFacetReadSerializer

    def perform_destroy(self, instance: ItemFacet) -> None:
        """Remove facet via service so cache invalidation fires."""
        remove_facet_from_item(item_facet=instance)


class ItemInstanceViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only listing of ItemInstance rows for a character's inventory.

    The wardrobe page uses this to render carried-but-not-worn items. The
    ``character`` query parameter filters to items whose ``game_object.location``
    is the requested character (i.e., currently held by them).

    Permission scoping (non-staff): only items located on a character the
    request user currently plays are returned. Staff see everything.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = ItemInstanceReadSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = ItemInstanceFilter
    pagination_class = ItemTemplatePagination
    queryset = (
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
                queryset=ItemFacet.objects.select_related("facet", "attachment_quality_tier"),
                to_attr="cached_item_facets",
            ),
        )
        .order_by("-pk")
    )

    def get_queryset(self) -> QuerySet[ItemInstance]:
        """Scope to items located on characters the request user plays."""
        qs = super().get_queryset()
        if self.request.user.is_staff:
            return qs
        character_ids = RosterEntry.objects.for_account(
            cast(AccountDB, self.request.user)
        ).values_list("character_sheet_id", flat=True)
        return qs.filter(game_object__db_location__id__in=character_ids)


class EquippedItemViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only ViewSet for EquippedItem (GET list/detail).

    Mutations (equip/unequip) flow through the unified action dispatcher
    via the ``execute_action`` websocket inputfunc — REST stays read-only.
    """

    serializer_class = EquippedItemReadSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = ItemTemplatePagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = EquippedItemFilter
    queryset = EquippedItem.objects.select_related(
        "item_instance",
        "item_instance__template",
        "character",
        "character__sheet_data",
    ).order_by("-pk")


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
        return _account_currently_plays(cast(AccountDB, request.user), sheet)

    def has_object_permission_for_player(
        self, request: Request, view: APIView, obj: Outfit
    ) -> bool:
        return _account_currently_plays(cast(AccountDB, request.user), obj.character_sheet)


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
        return _account_currently_plays(cast(AccountDB, request.user), outfit.character_sheet)

    def has_object_permission_for_player(
        self, request: Request, view: APIView, obj: OutfitSlot
    ) -> bool:
        return _account_currently_plays(cast(AccountDB, request.user), obj.outfit.character_sheet)


class OutfitViewSet(viewsets.ModelViewSet):
    """ViewSet for Outfit definitions (save / list / rename / delete).

    Save delegates to ``save_outfit`` (snapshots current loadout). PATCH
    updates the Outfit row directly. DELETE delegates to ``delete_outfit``.
    Per design, equip/unequip and apply/undress flow through the action
    dispatcher — this ViewSet only handles configuration CRUD.
    """

    permission_classes = [OutfitWritePermission]
    pagination_class = ItemTemplatePagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = OutfitFilter
    queryset = (
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
        .order_by("name")
    )

    def get_queryset(self) -> QuerySet[Outfit]:
        """Scope to outfits owned by characters the request user plays."""
        qs = super().get_queryset()
        if self.request.user.is_staff:
            return qs
        sheet_ids = RosterEntry.objects.for_account(cast(AccountDB, self.request.user)).values_list(
            "character_sheet_id", flat=True
        )
        return qs.filter(character_sheet_id__in=sheet_ids)

    def get_serializer_class(self) -> type[serializers.ModelSerializer]:
        """Use write serializer for create/update; read serializer otherwise."""
        if self.action in ("create", "update", "partial_update"):
            return OutfitWriteSerializer
        return OutfitReadSerializer

    def perform_destroy(self, instance: Outfit) -> None:
        """Delegate destruction to the delete_outfit service."""
        delete_outfit(instance)


class OutfitSlotViewSet(viewsets.ModelViewSet):
    """ViewSet for OutfitSlot create/list/delete.

    Flat per-slot endpoint (matches ``EquippedItemViewSet`` shape — one
    POST adds or replaces a single slot, one DELETE removes one slot).
    """

    http_method_names = ["get", "post", "delete", "head", "options"]
    permission_classes = [OutfitSlotWritePermission]
    pagination_class = ItemTemplatePagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = OutfitSlotFilter
    queryset = OutfitSlot.objects.select_related(
        "outfit",
        "outfit__character_sheet",
        "item_instance",
        "item_instance__template",
        "item_instance__quality_tier",
    ).order_by("body_region", "equipment_layer")

    def get_queryset(self) -> QuerySet[OutfitSlot]:
        """Scope to slots whose outfit belongs to a character the user plays."""
        qs = super().get_queryset()
        if self.request.user.is_staff:
            return qs
        sheet_ids = RosterEntry.objects.for_account(cast(AccountDB, self.request.user)).values_list(
            "character_sheet_id", flat=True
        )
        return qs.filter(outfit__character_sheet_id__in=sheet_ids)

    def get_serializer_class(self) -> type[serializers.ModelSerializer]:
        """Use write serializer for create; read serializer otherwise."""
        if self.action == "create":
            return OutfitSlotWriteSerializer
        return OutfitSlotReadSerializer

    def perform_destroy(self, instance: OutfitSlot) -> None:
        """Delegate destruction to remove_outfit_slot (idempotent)."""
        remove_outfit_slot(
            outfit=instance.outfit,
            body_region=instance.body_region,
            equipment_layer=instance.equipment_layer,
        )


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
