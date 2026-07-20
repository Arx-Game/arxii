"""URL routing for the worship API (#2355)."""

from rest_framework.routers import DefaultRouter

from world.worship.views import MiracleViewSet, WorshippedBeingViewSet

router = DefaultRouter()
router.register("beings", WorshippedBeingViewSet, basename="worshipped-being")
router.register("miracles", MiracleViewSet, basename="miracle")

app_name = "worship"
urlpatterns = router.urls
