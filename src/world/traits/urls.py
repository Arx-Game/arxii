"""
URL configuration for traits API.
"""

from rest_framework.routers import DefaultRouter

from world.traits.views import StatDefinitionsViewSet

router = DefaultRouter()
router.register(r"stat-definitions", StatDefinitionsViewSet, basename="stat-definition")

urlpatterns = router.urls
