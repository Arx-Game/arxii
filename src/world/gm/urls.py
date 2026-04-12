"""URL configuration for the GM system."""

from rest_framework.routers import DefaultRouter

from world.gm.views import GMApplicationViewSet

app_name = "gm"

router = DefaultRouter()
router.register("applications", GMApplicationViewSet, basename="gm-application")

urlpatterns = router.urls
