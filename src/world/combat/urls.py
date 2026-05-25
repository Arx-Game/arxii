"""URL configuration for combat API."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from world.combat.views import CombatEncounterViewSet
from world.combat.views_outcome_details import ActionOutcomeDetailsView

router = DefaultRouter()
router.register("", CombatEncounterViewSet, basename="combat-encounter")

app_name = "combat"
urlpatterns = [
    path(
        "action-outcome-details/",
        ActionOutcomeDetailsView.as_view(),
        name="action-outcome-details",
    ),
    *router.urls,
]
