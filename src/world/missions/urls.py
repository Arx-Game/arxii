"""URL configuration for the missions authoring API (Phase D)."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from world.missions.views import MissionTemplateViewSet

app_name = "missions"

router = DefaultRouter()
router.register(r"templates", MissionTemplateViewSet, basename="mission-template")

urlpatterns = [
    path("", include(router.urls)),
]
