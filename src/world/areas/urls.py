from django.urls import path
from rest_framework.routers import DefaultRouter

from world.areas.views import AreaViewSet, PresenceView, RoomProfileViewSet

router = DefaultRouter()
router.register("rooms", RoomProfileViewSet, basename="room")
router.register("", AreaViewSet, basename="area")

app_name = "areas"
urlpatterns = [
    path("presence/", PresenceView.as_view(), name="presence"),
    *router.urls,
]
