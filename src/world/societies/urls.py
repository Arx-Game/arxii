"""URLs for the societies player API (#761 — diegetic ranking boards)."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from world.societies.ranking_views import RankingDisplayViewSet

app_name = "societies"

router = DefaultRouter()
router.register(r"rankings", RankingDisplayViewSet, basename="ranking-display")

urlpatterns = [
    path("", include(router.urls)),
]
