"""
URL configuration for conditions API.

All endpoints are read-only. Conditions are applied through game logic,
not directly through the API.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from world.conditions.views import (
    CapabilityTypeViewSet,
    CharacterConditionsViewSet,
    CheckTypeViewSet,
    ConditionCategoryViewSet,
    ConditionTemplateViewSet,
    DamageTypeViewSet,
)

router = DefaultRouter()

# Lookup tables
router.register("categories", ConditionCategoryViewSet, basename="condition-category")
router.register("capabilities", CapabilityTypeViewSet, basename="capability-type")
router.register("check-types", CheckTypeViewSet, basename="check-type")
router.register("damage-types", DamageTypeViewSet, basename="damage-type")

# Condition templates
router.register("templates", ConditionTemplateViewSet, basename="condition-template")

# Character conditions (active instances)
router.register("character", CharacterConditionsViewSet, basename="character-conditions")

urlpatterns = [
    path("", include(router.urls)),
]
