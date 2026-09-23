"""URLs for the Almanach de Catenys API (#3983): the house-builder reads
(realm/founder reads open to any authenticated account; houses stay staff-only)."""

from rest_framework.routers import DefaultRouter

from world.societies.houses.almanach_views import (
    AlmanachHouseViewSet,
    AlmanachRealmViewSet,
    LandShapeViewSet,
)

router = DefaultRouter()
router.register(r"realms", AlmanachRealmViewSet, basename="almanach-realm")
router.register(r"houses", AlmanachHouseViewSet, basename="almanach-house")
router.register(r"land-shapes", LandShapeViewSet, basename="almanach-land-shape")

app_name = "almanach"
urlpatterns = router.urls
