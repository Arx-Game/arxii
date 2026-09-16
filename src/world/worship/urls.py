"""URL routing for the worship API (#2355)."""

from rest_framework.routers import DefaultRouter

from world.worship.views import MiracleViewSet, WorshippedBeingViewSet, WorshipRiteViewSet

router = DefaultRouter()
router.register("beings", WorshippedBeingViewSet, basename="worshipped-being")
router.register("miracles", MiracleViewSet, basename="miracle")
router.register("rites", WorshipRiteViewSet, basename="worship-rite")

app_name = "worship"
urlpatterns = router.urls
