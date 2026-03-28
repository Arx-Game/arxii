from rest_framework.routers import DefaultRouter

from world.areas.views import AreaViewSet

router = DefaultRouter()
router.register("", AreaViewSet, basename="area")

app_name = "areas"
urlpatterns = router.urls
