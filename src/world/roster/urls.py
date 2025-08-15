"""
URL patterns for the roster system API.
"""

from rest_framework.routers import DefaultRouter

from world.roster.views import (
    PlayerMailViewSet,
    PlayerMediaViewSet,
    RosterEntryViewSet,
    RosterTenureViewSet,
    RosterViewSet,
)

app_name = "roster"

router = DefaultRouter()
router.register("rosters", RosterViewSet, basename="rosters")
router.register("entries", RosterEntryViewSet, basename="entries")
router.register("media", PlayerMediaViewSet, basename="media")
router.register("mail", PlayerMailViewSet, basename="mail")
router.register("tenures", RosterTenureViewSet, basename="tenures")

urlpatterns = router.urls
