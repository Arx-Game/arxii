"""URL configuration for covenants API endpoints."""

from rest_framework.routers import DefaultRouter

from world.covenants.views import CharacterCovenantRoleViewSet, GearArchetypeCompatibilityViewSet

router = DefaultRouter()
router.register(
    "character-roles",
    CharacterCovenantRoleViewSet,
    basename="character-covenant-role",
)
router.register(
    "gear-compatibilities",
    GearArchetypeCompatibilityViewSet,
    basename="gear-compatibility",
)

urlpatterns = router.urls
