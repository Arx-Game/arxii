"""URL configuration for room_features (defense) API endpoints (#2177)."""

from rest_framework.routers import DefaultRouter

from world.room_features.views_defense import (
    DefenseInstallViewSet,
    ExitBarsViewSet,
    RoomAlarmViewSet,
    RoomWardViewSet,
)

router = DefaultRouter()
router.register("exit-bars", ExitBarsViewSet, basename="exit-bars")
router.register("room-wards", RoomWardViewSet, basename="room-ward")
router.register("room-alarms", RoomAlarmViewSet, basename="room-alarm")
router.register("defenses", DefenseInstallViewSet, basename="defense")

urlpatterns = router.urls
