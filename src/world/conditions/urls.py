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
    ConditionCategoryViewSet,
    ConditionInstanceViewSet,
    ConditionTemplateViewSet,
    DamageTypeViewSet,
)

router = DefaultRouter()

# Lookup tables
router.register("categories", ConditionCategoryViewSet, basename="condition-category")
router.register("capabilities", CapabilityTypeViewSet, basename="capability-type")
router.register("damage-types", DamageTypeViewSet, basename="damage-type")

# Condition templates
router.register("templates", ConditionTemplateViewSet, basename="condition-template")

# Character conditions (active instances)
router.register("character", CharacterConditionsViewSet, basename="character-conditions")

# Single condition instance retrieve (deep link target, #551)
router.register("instances", ConditionInstanceViewSet, basename="condition-instance")

urlpatterns = [
    path("", include(router.urls)),
]
