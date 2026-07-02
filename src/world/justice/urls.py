"""URL configuration for the justice API (#1765)."""

from rest_framework.routers import DefaultRouter

from world.justice.views import PersonaHeatViewSet

router = DefaultRouter()
router.register("heat", PersonaHeatViewSet, basename="persona-heat")

urlpatterns = [
    *router.urls,
]
