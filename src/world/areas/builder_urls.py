from rest_framework.routers import DefaultRouter

from world.areas.builder_views import WorldBuilderViewSet

router = DefaultRouter()
router.register("areas", WorldBuilderViewSet, basename="world-builder-area")

app_name = "world_builder"
urlpatterns = router.urls
