"""URL configuration for relationships API (#3957)."""

from rest_framework.routers import DefaultRouter

from world.relationships.views import RelationshipCapstoneViewSet, RelationshipConditionViewSet

app_name = "relationships"

router = DefaultRouter()
router.register("conditions", RelationshipConditionViewSet)
router.register(
    "relationship-capstones", RelationshipCapstoneViewSet, basename="relationship-capstone"
)

urlpatterns = router.urls
