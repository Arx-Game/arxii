"""URL configuration for covenants API endpoints."""

from rest_framework.routers import DefaultRouter

from world.covenants.views import GearArchetypeCompatibilityViewSet

router = DefaultRouter()
router.register(
    "gear-compatibilities",
    GearArchetypeCompatibilityViewSet,
    basename="gear-compatibility",
)

urlpatterns = router.urls
