"""
URL patterns for the character sheets API.
"""

from rest_framework.routers import DefaultRouter

from world.character_sheets.views import (
    CharacterSheetViewSet,
    HeritageViewSet,
    MoodOptionViewSet,
)

app_name = "character_sheets"

router = DefaultRouter()
# Before the sheet route: its catch-all "<pk>/" would otherwise swallow "mood-options/".
router.register("mood-options", MoodOptionViewSet, basename="mood-options")
router.register("heritages", HeritageViewSet, basename="heritages")
router.register("", CharacterSheetViewSet, basename="character-sheets")

urlpatterns = router.urls
