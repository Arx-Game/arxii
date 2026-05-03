"""API ViewSets for items."""

from typing import cast

from django.db.models import Prefetch, QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB
from rest_framework import serializers, viewsets
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
from world.items.services.appearance import visible_worn_items_for
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


def _is_own_character(user: AccountDB, target: ObjectDB) -> bool:
    """True if ``user`` currently plays ``target`` (active roster tenure)."""
    return RosterEntry.objects.for_account(user).filter(character_sheet_id=target.pk).exists()


def _account_characters_in_room(user: AccountDB, room: ObjectDB | None) -> bool:
    """True if any character ``user`` plays is currently in ``room``."""
    if room is None:
        return False
    return (
        RosterEntry.objects.for_account(user)
        .filter(character_sheet__character__db_location_id=room.pk)
        .exists()
    )


class VisibleWornItemViewSet(viewsets.ViewSet):
    """List visible worn items for a character.

    The ``character`` query parameter selects the target. Visibility scope:

    - same-room observer (any character on the requester's account is in
      the target's room), OR
    - self-look (the requester plays the target), OR
    - staff (bypass).

    Out-of-scope requesters get an empty list (200) — never a 403/404,
    to avoid leaking presence information about characters in rooms the
    observer can't see.

    The endpoint result is computed from ``visible_worn_items_for`` rather
    than a queryset, so this is a plain ``ViewSet`` with a ``list`` action.
    """

    permission_classes = [PlayerOrStaffPermission]
    filter_backends = [DjangoFilterBackend]
    filterset_class = VisibleWornItemFilter

    def list(self, request: Request) -> Response:
        """Return the slim visible-worn list for ``?character=<pk>``."""
        # The endpoint result is computed from a service, not from a queryset,
        # so we route the ``character`` parameter through the FilterSet's form
        # for validation/coercion rather than reading query_params directly.
        filterset = VisibleWornItemFilter(
            data=request.query_params,
            queryset=EquippedItem.objects.none(),
        )
        if not filterset.is_valid():
            return Response([])
        character_pk = filterset.form.cleaned_data.get("character")
        if not character_pk:
            return Response([])

        try:
            target = ObjectDB.objects.get(pk=character_pk)
        except ObjectDB.DoesNotExist:
            return Response([])

        user = cast(AccountDB, request.user)
        is_staff = bool(user.is_staff)
        is_self = not is_staff and _is_own_character(user, target)
        same_room = (
            not is_staff and not is_self and _account_characters_in_room(user, target.location)
        )
        if not (is_staff or is_self or same_room):
            return Response([])

        # Pick an observer that triggers the right bypass branch in the
        # service: staff → request user; self → the target itself (so
        # ``observer is character`` fires); same-room → request user (no bypass).
        if is_self:
            observer: object = target
        else:
            observer = user

        items = visible_worn_items_for(target, observer=observer)
        serializer = VisibleWornItemSerializer(items, many=True)
        return Response(serializer.data)


class VisibleItemDetailViewSet(viewsets.ReadOnlyModelViewSet):
    """Full ItemInstance detail for items currently visibly worn nearby.

    For staff, every item is returned (bypass). For non-staff, the queryset
    is filtered to items currently equipped on observable characters
    (own-account characters or characters sharing a room with one of the
    requester's characters), AND visible (concealed-by-layer items are
    filtered out so concealed items return 404 — we don't leak existence).

    The visibility filter walks one ``visible_worn_items_for`` call per
    observable character; in practice the requester is in one room with a
    small number of characters, so N is bounded.
    """

    permission_classes = [PlayerOrStaffPermission]
    serializer_class = ItemInstanceReadSerializer
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
        """Scope to currently-visible worn items the requester can observe."""
        qs = super().get_queryset()
        if self.request.user.is_staff:
            return qs
        return qs.filter(id__in=self._visible_item_ids())

    def _visible_item_ids(self) -> set[int]:
        """Item IDs currently visibly worn on characters the user can observe.

        Walks two RosterEntry querysets — own characters, and characters in
        the same rooms as own characters — both with ``select_related`` so
        that ``entry.character_sheet.character`` and its ``db_location`` are
        free to access. Then iterates ``character.equipped_items`` (the
        cached handler) for each character, which loads once per character
        and is free thereafter via the SharedMemoryModel identity map.

        Total query count: 2 RosterEntry queries + 1 EquippedItem load per
        observable character (cached on the handler), regardless of how many
        items each character is wearing.
        """
        user = cast(AccountDB, self.request.user)

        # Own characters — self-look bypasses layer hiding so concealed
        # items the user owns are still reachable via this endpoint.
        own_entries = list(
            RosterEntry.objects.for_account(user).select_related(
                "character_sheet__character__db_location",
            )
        )
        if not own_entries:
            return set()

        own_chars = [entry.character_sheet.character for entry in own_entries]
        own_pks = {character.pk for character in own_chars}
        own_locations = {
            character.db_location_id
            for character in own_chars
            if character.db_location_id is not None
        }

        # Same-room characters — anyone in a room where the user has at
        # least one of their own characters present. Layer hiding applies.
        if own_locations:
            same_room_entries = list(
                RosterEntry.objects.filter(
                    character_sheet__character__db_location_id__in=own_locations,
                ).select_related("character_sheet__character__db_location")
            )
            same_room_chars = [entry.character_sheet.character for entry in same_room_entries]
        else:
            same_room_chars = []

        visible_ids: set[int] = set()
        seen_pks: set[int] = set()
        for character in (*own_chars, *same_room_chars):
            if character.pk in seen_pks:
                continue
            seen_pks.add(character.pk)
            # Self-look bypass: pass the character itself as observer so
            # ``observer is character`` fires inside the service. Same-room
            # observers pass the user, which applies hiding.
            observer: object = character if character.pk in own_pks else user
            for entry in visible_worn_items_for(character, observer=observer):
                visible_ids.add(entry.item_instance.pk)
        return visible_ids
