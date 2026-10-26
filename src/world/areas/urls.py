from django.urls import path
from rest_framework.routers import DefaultRouter

from world.areas.views import AreaViewSet, FeatureTypeViewSet, PresenceView, RoomProfileViewSet

router = DefaultRouter()
router.register("rooms", RoomProfileViewSet, basename="room")
# Before the area catch-all, whose detail route would swallow "feature-types/".
router.register("feature-types", FeatureTypeViewSet, basename="feature-type")
router.register("", AreaViewSet, basename="area")

app_name = "areas"
urlpatterns = [
    path("presence/", PresenceView.as_view(), name="presence"),
    *router.urls,
]
