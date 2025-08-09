"""
URL patterns for the roster system API.
"""

from rest_framework.routers import DefaultRouter

from world.roster.views import RosterEntryViewSet, RosterViewSet

app_name = "roster"

router = DefaultRouter()
router.register("rosters", RosterViewSet, basename="rosters")
router.register("entries", RosterEntryViewSet, basename="entries")

urlpatterns = router.urls
