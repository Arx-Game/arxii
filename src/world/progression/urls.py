"""
URL configuration for progression API endpoints.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from world.progression.views import (
    AccountProgressionView,
    ClaimKudosView,
    PathIntentViewSet,
    RandomSceneViewSet,
    VoteViewSet,
)

router = DefaultRouter()
router.register("votes", VoteViewSet, basename="vote")
router.register("random-scenes", RandomSceneViewSet, basename="random-scene")

_path_intent_view = PathIntentViewSet.as_view(
    {
        "get": "list",
        "put": "update",
        "delete": "destroy",
    }
)

urlpatterns = [
    path("account/", AccountProgressionView.as_view(), name="account-progression"),
    path("claim-kudos/", ClaimKudosView.as_view(), name="claim-kudos"),
    path("path-intent/", _path_intent_view, name="path-intent"),
    path("", include(router.urls)),
]
