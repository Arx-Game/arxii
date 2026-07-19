"""URL routing for the ceremonies API (#2289)."""

from rest_framework.routers import DefaultRouter

from world.ceremonies.views import CeremonyViewSet, SeanceOfferViewSet

router = DefaultRouter()
router.register("ceremonies", CeremonyViewSet, basename="ceremony")
router.register("seance-offers", SeanceOfferViewSet, basename="seance-offer")

app_name = "ceremonies"
urlpatterns = router.urls
