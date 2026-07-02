"""URL routes for the building-manager read API (#670 PR2)."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from world.buildings.views import (
    BuildingManagerViewSet,
    DecorationTemplateViewSet,
    RoomSizeTierViewSet,
)

app_name = "buildings"

router = DefaultRouter()
router.register(r"manager", BuildingManagerViewSet, basename="building-manager")
router.register(r"room-size-tiers", RoomSizeTierViewSet, basename="room-size-tier")
router.register(r"decoration-templates", DecorationTemplateViewSet, basename="decoration-template")

urlpatterns = [path("", include(router.urls))]
