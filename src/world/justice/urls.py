"""URL configuration for the justice API (#1765, #1826)."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from world.justice.views import (
    BribeView,
    LieLowView,
    PardonView,
    PersonaHeatViewSet,
    WantedListView,
)

router = DefaultRouter()
router.register("heat", PersonaHeatViewSet, basename="persona-heat")

urlpatterns = [
    path("lie-low/", LieLowView.as_view(), name="justice-lie-low"),
    path("bribe/", BribeView.as_view(), name="justice-bribe"),
    path("pardon/", PardonView.as_view(), name="justice-pardon"),
    path("wanted/", WantedListView.as_view(), name="justice-wanted"),
    *router.urls,
]
