"""URL configuration for items API endpoints."""

from rest_framework.routers import DefaultRouter

from world.items.views import (
    EquippedItemViewSet,
    FashionJudgementViewSet,
    FashionPresentationViewSet,
    InteractionTypeViewSet,
    ItemFacetViewSet,
    ItemInstanceViewSet,
    ItemStyleCraftViewSet,
    ItemTemplateViewSet,
    OutfitSlotViewSet,
    OutfitViewSet,
    QualityTierViewSet,
    VisibleItemDetailViewSet,
    VisibleWornItemViewSet,
)

router = DefaultRouter()
router.register("quality-tiers", QualityTierViewSet, basename="quality-tier")
router.register("interaction-types", InteractionTypeViewSet, basename="interaction-type")
router.register("templates", ItemTemplateViewSet, basename="item-template")
router.register("item-facets", ItemFacetViewSet, basename="item-facet")
router.register("item-styles", ItemStyleCraftViewSet, basename="item-style")
router.register("equipped-items", EquippedItemViewSet, basename="equipped-item")
router.register("inventory", ItemInstanceViewSet, basename="item-instance")
router.register("outfits", OutfitViewSet, basename="outfit")
router.register("outfit-slots", OutfitSlotViewSet, basename="outfit-slot")
router.register("visible-worn", VisibleWornItemViewSet, basename="visible-worn")
router.register(
    "visible-item-detail",
    VisibleItemDetailViewSet,
    basename="visible-item-detail",
)
router.register(
    "fashion-presentations",
    FashionPresentationViewSet,
    basename="fashion-presentation",
)
router.register(
    "fashion-judgements",
    FashionJudgementViewSet,
    basename="fashion-judgement",
)

urlpatterns = router.urls
