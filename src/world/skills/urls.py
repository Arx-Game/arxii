"""
Skills API URL configuration.
"""

from rest_framework.routers import DefaultRouter

from world.skills.views import (
    PathSkillSuggestionViewSet,
    SkillPointBudgetViewSet,
    SkillViewSet,
    SpecializationViewSet,
)

router = DefaultRouter()
router.register("skills", SkillViewSet, basename="skill")
router.register("specializations", SpecializationViewSet, basename="specialization")
router.register(
    "path-skill-suggestions",
    PathSkillSuggestionViewSet,
    basename="path-skill-suggestion",
)
router.register("skill-budget", SkillPointBudgetViewSet, basename="skill-budget")

urlpatterns = router.urls
