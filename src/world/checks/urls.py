"""URL configuration for checks API."""

from rest_framework.routers import DefaultRouter

from world.checks.views import CheckTypeViewSet, ConsequenceOutcomeViewSet

router = DefaultRouter()
router.register("check-types", CheckTypeViewSet, basename="check-type")
router.register("consequence-outcomes", ConsequenceOutcomeViewSet, basename="consequence-outcome")

app_name = "checks"
urlpatterns = router.urls
