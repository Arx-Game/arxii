"""URL configuration for checks API."""

from rest_framework.routers import DefaultRouter

from world.checks.views import (
    CheckCallTargetViewSet,
    CheckTypeViewSet,
    ConsequenceOutcomeViewSet,
    PlayerCheckTypeViewSet,
)

router = DefaultRouter()
router.register("check-types", CheckTypeViewSet, basename="check-type")
router.register("player-check-types", PlayerCheckTypeViewSet, basename="player-check-type")
router.register("check-call-targets", CheckCallTargetViewSet, basename="check-call-target")
router.register("consequence-outcomes", ConsequenceOutcomeViewSet, basename="consequence-outcome")

app_name = "checks"
urlpatterns = router.urls
