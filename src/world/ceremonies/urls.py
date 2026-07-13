"""URL routing for the ceremonies API (#2289)."""

from rest_framework.routers import DefaultRouter

from world.ceremonies.views import CeremonyViewSet

router = DefaultRouter()
router.register("ceremonies", CeremonyViewSet, basename="ceremony")

app_name = "ceremonies"
urlpatterns = router.urls
