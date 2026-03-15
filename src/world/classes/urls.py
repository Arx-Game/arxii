"""
Classes API URL configuration.
"""

from rest_framework.routers import DefaultRouter

from world.classes.views import AspectViewSet, CharacterClassViewSet, PathViewSet

router = DefaultRouter()
router.register("paths", PathViewSet, basename="path")
router.register("classes", CharacterClassViewSet, basename="character-class")
router.register("aspects", AspectViewSet, basename="aspect")

urlpatterns = router.urls
