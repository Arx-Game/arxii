"""URL configuration for combat API."""

from rest_framework.routers import DefaultRouter

from world.combat.views import CombatEncounterViewSet

router = DefaultRouter()
router.register("", CombatEncounterViewSet, basename="combat-encounter")

app_name = "combat"
urlpatterns = router.urls
