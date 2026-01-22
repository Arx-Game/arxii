"""
URL configuration for the goals API.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from world.goals.views import (
    CharacterGoalViewSet,
    GoalDomainViewSet,
    GoalJournalViewSet,
)

app_name = "goals"

router = DefaultRouter()
router.register(r"domains", GoalDomainViewSet, basename="goal-domain")

urlpatterns = [
    # Router-based URLs
    path("", include(router.urls)),
    # Character goals
    path(
        "my-goals/",
        CharacterGoalViewSet.as_view({"get": "list"}),
        name="my-goals-list",
    ),
    path(
        "my-goals/update/",
        CharacterGoalViewSet.as_view({"post": "update_all"}),
        name="my-goals-update",
    ),
    # Journals
    path(
        "journals/",
        GoalJournalViewSet.as_view({"get": "list", "post": "create"}),
        name="journals-list",
    ),
    path(
        "journals/public/",
        GoalJournalViewSet.as_view({"get": "public"}),
        name="journals-public",
    ),
]
