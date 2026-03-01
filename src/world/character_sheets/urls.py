"""
URL patterns for the character sheets API.
"""

from rest_framework.routers import DefaultRouter

from world.character_sheets.views import CharacterSheetViewSet

app_name = "character_sheets"

router = DefaultRouter()
router.register("", CharacterSheetViewSet, basename="character-sheets")

urlpatterns = router.urls
