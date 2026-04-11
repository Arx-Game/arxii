"""URL configuration for player submissions API."""

from rest_framework.routers import DefaultRouter

from world.player_submissions.views import (
    BugReportViewSet,
    PlayerFeedbackViewSet,
    PlayerReportViewSet,
)

router = DefaultRouter()
router.register("feedback", PlayerFeedbackViewSet, basename="player-feedback")
router.register("bug-reports", BugReportViewSet, basename="bug-report")
router.register("player-reports", PlayerReportViewSet, basename="player-report")

app_name = "player_submissions"
urlpatterns = router.urls
