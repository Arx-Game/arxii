"""URL configuration for the ships API (#1832 Task 10)."""

from __future__ import annotations

from rest_framework.routers import DefaultRouter

from world.ships.views import ShipTypeViewSet, ShipViewSet

router = DefaultRouter()
router.register("ships", ShipViewSet, basename="ship")
router.register("ship-types", ShipTypeViewSet, basename="ship-type")

urlpatterns = router.urls
