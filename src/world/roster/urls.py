"""
URL patterns for the roster system API.
"""

from rest_framework.routers import DefaultRouter

from world.roster.views import (
    FamilyMemberViewSet,
    FamilyViewSet,
    PlayerMailViewSet,
    PlayerMediaViewSet,
    RosterEntryViewSet,
    RosterTenureViewSet,
    RosterViewSet,
    TenureGalleryViewSet,
)

app_name = "roster"

router = DefaultRouter()
router.register("rosters", RosterViewSet, basename="rosters")
router.register("entries", RosterEntryViewSet, basename="entries")
router.register("families", FamilyViewSet, basename="families")
router.register("family-members", FamilyMemberViewSet, basename="family-members")
router.register("media", PlayerMediaViewSet, basename="media")
router.register("mail", PlayerMailViewSet, basename="mail")
router.register("tenures", RosterTenureViewSet, basename="tenures")
router.register("galleries", TenureGalleryViewSet, basename="galleries")

urlpatterns = router.urls
