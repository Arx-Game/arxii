"""URL configuration for mechanics API."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from world.mechanics.views import (
    AvailableActionsView,
    ChallengeInstanceViewSet,
    ChallengeTemplateViewSet,
    CharacterModifierViewSet,
    ModifierCategoryViewSet,
    ModifierTargetViewSet,
    SituationInstanceViewSet,
    SituationTemplateViewSet,
)

app_name = "mechanics"

router = DefaultRouter()
router.register(r"categories", ModifierCategoryViewSet, basename="modifier-category")
router.register(r"modifier-targets", ModifierTargetViewSet, basename="modifier-target")
router.register(r"character-modifiers", CharacterModifierViewSet, basename="character-modifier")
router.register(r"challenge-templates", ChallengeTemplateViewSet, basename="challenge-template")
router.register(r"challenge-instances", ChallengeInstanceViewSet, basename="challenge-instance")
router.register(r"situation-templates", SituationTemplateViewSet, basename="situation-template")
router.register(r"situation-instances", SituationInstanceViewSet, basename="situation-instance")

urlpatterns = [
    path(
        "characters/<int:character_id>/available-actions/",
        AvailableActionsView.as_view(),
        name="available-actions",
    ),
    path("", include(router.urls)),
]
