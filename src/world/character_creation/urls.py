"""
Character Creation URL configuration.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from world.character_creation.views import (
    CanCreateCharacterView,
    CharacterDraftViewSet,
    FamilyViewSet,
    GenderViewSet,
    PronounsViewSet,
    SpeciesViewSet,
    StartingAreaViewSet,
)

app_name = "character_creation"

router = DefaultRouter()
router.register("starting-areas", StartingAreaViewSet, basename="starting-area")
router.register("species", SpeciesViewSet, basename="species")
router.register("families", FamilyViewSet, basename="family")
router.register("genders", GenderViewSet, basename="gender")
router.register("pronouns", PronounsViewSet, basename="pronouns")
router.register("drafts", CharacterDraftViewSet, basename="draft")

urlpatterns = [
    # Router-based URLs
    path("", include(router.urls)),
    # Standalone eligibility check
    path("can-create/", CanCreateCharacterView.as_view(), name="can-create"),
]
