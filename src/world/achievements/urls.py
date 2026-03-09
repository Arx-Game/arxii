"""URL routing for achievements API."""

from rest_framework.routers import DefaultRouter

from world.achievements.views import AchievementViewSet, CharacterAchievementViewSet

router = DefaultRouter()
router.register("achievements", AchievementViewSet, basename="achievement")
router.register(
    "character-achievements", CharacterAchievementViewSet, basename="character-achievement"
)

app_name = "achievements"
urlpatterns = router.urls
