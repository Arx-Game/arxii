"""URLs for the Almanach de Catenys API (#3983): staff-only house-builder reads."""

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
