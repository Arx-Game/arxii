from rest_framework.routers import DefaultRouter

from world.areas.builder_views import WorldBuilderViewSet
from world.areas.worldmap.views import RegionMapViewSet

router = DefaultRouter()
router.register("areas", WorldBuilderViewSet, basename="world-builder-area")
router.register("region-maps", RegionMapViewSet, basename="region-map")

app_name = "world_builder"
urlpatterns = router.urls
