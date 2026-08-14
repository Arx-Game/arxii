"""
Species API URL configuration.
"""

from rest_framework.routers import DefaultRouter

from world.species.views import MyLanguagesViewSet

router = DefaultRouter()
router.register("my-languages", MyLanguagesViewSet, basename="my-language")

urlpatterns = router.urls
