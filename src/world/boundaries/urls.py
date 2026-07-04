"""URL patterns for the boundaries API (#1771)."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from world.boundaries.views import (
    ContentThemeViewSet,
    PlayerBoundaryViewSet,
    SceneLinesAndVeilsView,
    TreasuredSubjectViewSet,
)

router = DefaultRouter()
router.register("content-themes", ContentThemeViewSet, basename="content-themes")
router.register("player-boundaries", PlayerBoundaryViewSet, basename="player-boundaries")
router.register("treasured-subjects", TreasuredSubjectViewSet, basename="treasured-subjects")

urlpatterns = [
    *router.urls,
    path(
        "scenes/<int:scene_id>/lines-and-veils/",
        SceneLinesAndVeilsView.as_view(),
        name="scene-lines-and-veils",
    ),
]
