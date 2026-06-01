"""URL configuration for the missions authoring API (Phase D)."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from world.missions.views import (
    MissionCategoryViewSet,
    MissionGiverOfferingViewSet,
    MissionGiverViewSet,
    MissionInstanceViewSet,
    MissionNodeViewSet,
    MissionOptionRouteCandidateViewSet,
    MissionOptionRouteRewardViewSet,
    MissionOptionRouteViewSet,
    MissionOptionViewSet,
    MissionTemplateViewSet,
    PredicateLeafCatalogViewSet,
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
# D3 giver library — staff CRUD for the offer-side surface.
router.register(r"givers", MissionGiverViewSet, basename="mission-giver")
router.register(
    r"giver-offerings",
    MissionGiverOfferingViewSet,
    basename="mission-giver-offering",
)
# D4.3 staff-power instance ops (list/retrieve/destroy only).
router.register(r"instances", MissionInstanceViewSet, basename="mission-instance")
# D4 category browse (read-only; drives the category multi-select in Mission Studio).
router.register(r"categories", MissionCategoryViewSet, basename="missioncategory")
# D5 predicate-leaf catalog (read-only; drives the Studio builder palette).
router.register(r"predicate-leaves", PredicateLeafCatalogViewSet, basename="mission-predicate-leaf")

urlpatterns = [
    path("", include(router.urls)),
]
