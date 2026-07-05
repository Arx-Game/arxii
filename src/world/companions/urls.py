"""URL configuration for the companions API (#672)."""

from __future__ import annotations

from rest_framework.routers import DefaultRouter

from world.companions.views import CompanionArchetypeViewSet, CompanionViewSet

router = DefaultRouter()
router.register("companions", CompanionViewSet, basename="companion")
router.register("companion-archetypes", CompanionArchetypeViewSet, basename="companion-archetype")

urlpatterns = router.urls
