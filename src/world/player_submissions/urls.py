"""URL configuration for player submissions API."""

from rest_framework.routers import DefaultRouter

from world.player_submissions.views import (
    BugReportViewSet,
    PetitionViewSet,
    PlayerFeedbackViewSet,
    PlayerReportViewSet,
    SystemErrorReportViewSet,
)

router = DefaultRouter()
router.register("feedback", PlayerFeedbackViewSet, basename="player-feedback")
router.register("bug-reports", BugReportViewSet, basename="bug-report")
router.register("player-reports", PlayerReportViewSet, basename="player-report")
router.register("system-errors", SystemErrorReportViewSet, basename="system-error")

app_name = "player_submissions"
router.register("petitions", PetitionViewSet, basename="petition")

urlpatterns = router.urls
