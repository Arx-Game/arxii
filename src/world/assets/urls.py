"""URL configuration for the assets API (#1872)."""

from __future__ import annotations

from rest_framework.routers import DefaultRouter

from world.assets.views import NPCAssetViewSet

router = DefaultRouter()
router.register("", NPCAssetViewSet, basename="npc-asset")

urlpatterns = router.urls
