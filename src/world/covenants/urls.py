"""URL configuration for covenants API endpoints."""

from rest_framework.routers import DefaultRouter

from world.covenants.views import (
    CharacterCovenantRoleViewSet,
    CovenantLevelThresholdViewSet,
    CovenantRoleViewSet,
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
# Staff-authored lookup table: available roles per covenant type.
# Supports ?covenant_type= filtering for ritual form pickers.
router.register(
    "roles",
    CovenantRoleViewSet,
    basename="covenant-role",
)
# Legend-threshold lookup table: legend required to reach each covenant level.
router.register(
    "level-thresholds",
    CovenantLevelThresholdViewSet,
    basename="covenant-level-threshold",
)

urlpatterns = router.urls
