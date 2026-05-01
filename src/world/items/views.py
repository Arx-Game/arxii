"""API ViewSets for items."""

from django.db.models import Prefetch, QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import serializers, viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import SAFE_METHODS, IsAuthenticated
from rest_framework.request import Request
from rest_framework.views import APIView

from world.items.filters import (
    EquippedItemFilter,
    InteractionTypeFilter,
    ItemFacetFilter,
    ItemInstanceFilter,
    ItemTemplateFilter,
    QualityTierFilter,
)
from world.items.models import (
    EquippedItem,
    InteractionType,
    ItemFacet,
    ItemInstance,
    ItemTemplate,
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
    QualityTierSerializer,
)
from world.items.services.facets import remove_facet_from_item


class ItemFacetWritePermission(IsAuthenticated):
    """Allow attach/remove only if the user owns the item_instance, or is staff."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        if not super().has_permission(request, view):
            return False
        if request.method in SAFE_METHODS:
            return True
        if request.user.is_staff:
            return True
        # POST: check the item_instance the request is targeting.
        if request.method == "POST":
            instance_pk = request.data.get("item_instance")
            if instance_pk is None:
                # If item_instance is absent or unparseable, fall through to True;
                # the serializer's required-field validation will reject.
                return True
            return ItemInstance.objects.filter(pk=instance_pk, owner=request.user).exists()
        return True  # DELETE checked at object level

    def has_object_permission(self, request: Request, view: APIView, obj: ItemFacet) -> bool:
        if request.user.is_staff:
            return True
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
