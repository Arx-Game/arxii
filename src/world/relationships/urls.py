"""URL configuration for relationships API (#3957)."""

from rest_framework.routers import DefaultRouter

from world.relationships.views import (
    CharacterRelationshipViewSet,
    RelationshipCapstoneViewSet,
    RelationshipConditionViewSet,
    RelationshipTypeViewSet,
)

app_name = "relationships"

router = DefaultRouter()
router.register("conditions", RelationshipConditionViewSet)
router.register("types", RelationshipTypeViewSet, basename="relationship-type")
router.register("relationships", CharacterRelationshipViewSet, basename="relationship")
router.register(
    "relationship-capstones", RelationshipCapstoneViewSet, basename="relationship-capstone"
)

urlpatterns = router.urls
