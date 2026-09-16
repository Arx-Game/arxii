"""URL routing for the worship API (#2355)."""

from rest_framework.routers import DefaultRouter

from world.worship.staff_views import StaffBeingViewSet
from world.worship.views import (
    MiracleViewSet,
    PrayerViewSet,
    VisionViewSet,
    WorshippedBeingViewSet,
    WorshipRiteViewSet,
)

router = DefaultRouter()
router.register("beings", WorshippedBeingViewSet, basename="worshipped-being")
router.register("miracles", MiracleViewSet, basename="miracle")
router.register("rites", WorshipRiteViewSet, basename="worship-rite")
router.register("prayers", PrayerViewSet, basename="prayer")
router.register("visions", VisionViewSet, basename="vision")
router.register("admin/beings", StaffBeingViewSet, basename="staff-being")

app_name = "worship"
urlpatterns = router.urls
