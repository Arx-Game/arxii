"""URL routing for the being pacts API (#4341)."""

from rest_framework.routers import DefaultRouter

from world.pacts.views import PactCardViewSet

router = DefaultRouter()
router.register("cards", PactCardViewSet, basename="pact-card")

app_name = "pacts"
urlpatterns = router.urls
