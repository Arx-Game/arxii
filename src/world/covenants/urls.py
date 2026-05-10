"""URL configuration for covenants API endpoints."""

from rest_framework.routers import DefaultRouter

from world.covenants.views import (
    CharacterCovenantRoleViewSet,
    CovenantViewSet,
    GearArchetypeCompatibilityViewSet,
)

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
# Registered at "covenants" → /api/covenants/covenants/ (doubled path mirrors the
# existing sibling scheme: character-roles, gear-compatibilities, covenants all live
# under the /api/covenants/ prefix).
router.register(
    "covenants",
    CovenantViewSet,
    basename="covenant",
)

urlpatterns = router.urls
