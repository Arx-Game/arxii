"""URL configuration for items API endpoints."""

from rest_framework.routers import DefaultRouter

from world.items.market.views import MarketSquareViewSet, ServiceOfferViewSet
from world.items.views import (
    EquippedItemViewSet,
    FashionJudgementViewSet,
    FashionPresentationViewSet,
    InteractionTypeViewSet,
    ItemCreateCraftViewSet,
    ItemFacetViewSet,
    ItemInstanceViewSet,
    ItemStyleCraftViewSet,
    ItemTemplateViewSet,
    OutfitSlotViewSet,
    OutfitViewSet,
    QualityTierViewSet,
    ReclamationClaimViewSet,
    StyleViewSet,
    VisibleItemDetailViewSet,
    VisibleWornItemViewSet,
)
from world.items.views_station import LabStationViewSet

router = DefaultRouter()
router.register("quality-tiers", QualityTierViewSet, basename="quality-tier")
router.register("styles", StyleViewSet, basename="style")
router.register("market-squares", MarketSquareViewSet, basename="market-square")
router.register("service-offers", ServiceOfferViewSet, basename="service-offer")
router.register("interaction-types", InteractionTypeViewSet, basename="interaction-type")
router.register("reclamation-claims", ReclamationClaimViewSet, basename="reclamation-claim")
router.register("templates", ItemTemplateViewSet, basename="item-template")
router.register("item-facets", ItemFacetViewSet, basename="item-facet")
router.register("item-styles", ItemStyleCraftViewSet, basename="item-style")
router.register("crafting/create", ItemCreateCraftViewSet, basename="item-craft-create")
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
router.register("lab-stations", LabStationViewSet, basename="lab-station")

urlpatterns = router.urls
