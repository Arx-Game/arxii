"""URL configuration for relationships API."""

from rest_framework.routers import DefaultRouter

from world.relationships.views import (
    CharacterRelationshipViewSet,
    HybridRelationshipTypeViewSet,
    RelationshipConditionViewSet,
    RelationshipTrackViewSet,
)

app_name = "relationships"

router = DefaultRouter()
router.register("conditions", RelationshipConditionViewSet)
router.register("tracks", RelationshipTrackViewSet)
router.register("hybrid-types", HybridRelationshipTypeViewSet)
router.register("relationships", CharacterRelationshipViewSet, basename="relationship")

urlpatterns = router.urls
