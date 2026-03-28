from rest_framework.routers import DefaultRouter

from world.areas.views import AreaViewSet, RoomProfileViewSet

router = DefaultRouter()
router.register("rooms", RoomProfileViewSet, basename="room")
router.register("", AreaViewSet, basename="area")

app_name = "areas"
urlpatterns = router.urls
