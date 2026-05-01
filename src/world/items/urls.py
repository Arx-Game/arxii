"""URL configuration for items API endpoints."""

from rest_framework.routers import DefaultRouter

from world.items.views import (
    EquippedItemViewSet,
    InteractionTypeViewSet,
    ItemFacetViewSet,
    ItemInstanceViewSet,
    ItemTemplateViewSet,
    OutfitSlotViewSet,
    OutfitViewSet,
    QualityTierViewSet,
)

router = DefaultRouter()
router.register("quality-tiers", QualityTierViewSet, basename="quality-tier")
router.register("interaction-types", InteractionTypeViewSet, basename="interaction-type")
router.register("templates", ItemTemplateViewSet, basename="item-template")
router.register("item-facets", ItemFacetViewSet, basename="item-facet")
router.register("equipped-items", EquippedItemViewSet, basename="equipped-item")
router.register("inventory", ItemInstanceViewSet, basename="item-instance")
router.register("outfits", OutfitViewSet, basename="outfit")
router.register("outfit-slots", OutfitSlotViewSet, basename="outfit-slot")

urlpatterns = router.urls
