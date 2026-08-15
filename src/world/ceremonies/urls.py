"""URL routing for the ceremonies API (#2289)."""

from rest_framework.routers import DefaultRouter

from world.ceremonies.views import CeremonyViewSet, ConversionOfferViewSet, SeanceOfferViewSet

router = DefaultRouter()
router.register("ceremonies", CeremonyViewSet, basename="ceremony")
router.register("seance-offers", SeanceOfferViewSet, basename="seance-offer")
router.register("conversion-offers", ConversionOfferViewSet, basename="conversion-offer")

app_name = "ceremonies"
urlpatterns = router.urls
