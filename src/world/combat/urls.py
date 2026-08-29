"""URL configuration for combat API."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from world.combat.views import (
    CombatEncounterViewSet,
    CreatureTemplateViewSet,
    DuelChallengeViewSet,
    ThreatPoolViewSet,
)
from world.combat.views_outcome_details import ActionOutcomeDetailsView

router = DefaultRouter()
# Register before the empty-prefix encounter route: the encounter detail regex
# ``^(?P<pk>[^/.]+)/$`` would otherwise capture ``duel-challenges/``/``threat-pools/``/
# ``creature-templates/`` as a pk.
router.register("duel-challenges", DuelChallengeViewSet, basename="duel-challenge")
router.register("threat-pools", ThreatPoolViewSet, basename="threat-pool")
router.register("creature-templates", CreatureTemplateViewSet, basename="creature-template")
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
