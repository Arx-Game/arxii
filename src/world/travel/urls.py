"""URL routes for the overworld travel API (#2352)."""

from __future__ import annotations

from rest_framework.routers import DefaultRouter

from world.travel.views import (
    TravelHubViewSet,
    TravelMethodViewSet,
    VoyageInviteViewSet,
    VoyageViewSet,
)

router = DefaultRouter()
router.register(r"hubs", TravelHubViewSet, basename="travelhub")
router.register(r"methods", TravelMethodViewSet, basename="travelmethod")
router.register(r"voyages", VoyageViewSet, basename="voyage")
router.register(r"invites", VoyageInviteViewSet, basename="voyageinvite")

urlpatterns = router.urls
