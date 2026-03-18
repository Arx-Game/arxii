"""URL configuration for items API endpoints."""

from rest_framework.routers import DefaultRouter

from world.items.views import (
    InteractionTypeViewSet,
    ItemTemplateViewSet,
    QualityTierViewSet,
)

router = DefaultRouter()
router.register("quality-tiers", QualityTierViewSet, basename="quality-tier")
router.register("interaction-types", InteractionTypeViewSet, basename="interaction-type")
router.register("templates", ItemTemplateViewSet, basename="item-template")

urlpatterns = router.urls
