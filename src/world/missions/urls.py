"""URL configuration for the missions authoring API (Phase D)."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from world.missions.views import (
    MissionNodeViewSet,
    MissionOptionRouteCandidateViewSet,
    MissionOptionRouteRewardViewSet,
    MissionOptionRouteViewSet,
    MissionOptionViewSet,
    MissionTemplateViewSet,
)

app_name = "missions"

router = DefaultRouter()
router.register(r"templates", MissionTemplateViewSet, basename="mission-template")
# D2 editor CRUD — flat routes; clients filter by parent FK via query
# params (?template=…, ?node=…, ?option=…, ?route=…). Nested routes
# considered (drf-nested-routers) but flat + filter is simpler and the
# Mission Studio frontend can build either shape.
router.register(r"nodes", MissionNodeViewSet, basename="mission-node")
router.register(r"options", MissionOptionViewSet, basename="mission-option")
router.register(r"routes", MissionOptionRouteViewSet, basename="mission-option-route")
router.register(
    r"route-candidates",
    MissionOptionRouteCandidateViewSet,
    basename="mission-option-route-candidate",
)
router.register(
    r"route-rewards",
    MissionOptionRouteRewardViewSet,
    basename="mission-option-route-reward",
)

urlpatterns = [
    path("", include(router.urls)),
]
