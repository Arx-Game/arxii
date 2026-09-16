"""URL routing for the worship API (#2355)."""

from rest_framework.routers import DefaultRouter

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

app_name = "worship"
urlpatterns = router.urls
