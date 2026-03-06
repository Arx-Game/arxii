"""
URL configuration for mechanics API.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from world.mechanics.views import (
    CharacterModifierViewSet,
    ModifierCategoryViewSet,
    ModifierTargetViewSet,
)

app_name = "mechanics"

router = DefaultRouter()
router.register(r"categories", ModifierCategoryViewSet, basename="modifier-category")
router.register(r"modifier-targets", ModifierTargetViewSet, basename="modifier-target")
router.register(r"character-modifiers", CharacterModifierViewSet, basename="character-modifier")

urlpatterns = [
    path("", include(router.urls)),
]
