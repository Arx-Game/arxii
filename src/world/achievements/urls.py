"""URL routing for achievements API."""

from rest_framework.routers import DefaultRouter

from world.achievements.views import (
    AchievementViewSet,
    CharacterAchievementViewSet,
    PersonaTitleViewSet,
)

router = DefaultRouter()
router.register("achievements", AchievementViewSet, basename="achievement")
router.register(
    "character-achievements", CharacterAchievementViewSet, basename="character-achievement"
)
router.register("persona-titles", PersonaTitleViewSet, basename="persona-title")

app_name = "achievements"
urlpatterns = router.urls
