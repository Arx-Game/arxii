"""
Character Creation URL configuration.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from world.character_creation.views import (
    BeginningsViewSet,
    CanCreateCharacterView,
    CGPointBudgetViewSet,
    CharacterDraftViewSet,
    DraftAnimaRitualViewSet,
    DraftApplicationViewSet,
    DraftGiftViewSet,
    DraftMotifResonanceAssociationViewSet,
    DraftMotifResonanceViewSet,
    DraftMotifViewSet,
    DraftTechniqueViewSet,
    FormOptionsView,
    GenderViewSet,
    PathViewSet,
    PronounsViewSet,
    SpeciesViewSet,
    StartingAreaViewSet,
)
from world.roster.views import FamilyViewSet

app_name = "character_creation"

router = DefaultRouter()
router.register("starting-areas", StartingAreaViewSet, basename="starting-area")
router.register("beginnings", BeginningsViewSet, basename="beginnings")
router.register("species", SpeciesViewSet, basename="species")
router.register("cg-budgets", CGPointBudgetViewSet, basename="cg-budget")
router.register("families", FamilyViewSet, basename="family")
router.register("genders", GenderViewSet, basename="gender")
router.register("pronouns", PronounsViewSet, basename="pronouns")
router.register("paths", PathViewSet, basename="path")
router.register("drafts", CharacterDraftViewSet, basename="draft")
router.register("draft-gifts", DraftGiftViewSet, basename="draft-gift")
router.register("draft-techniques", DraftTechniqueViewSet, basename="draft-technique")
router.register("draft-motifs", DraftMotifViewSet, basename="draft-motif")
router.register(
    "draft-motif-resonances", DraftMotifResonanceViewSet, basename="draft-motif-resonance"
)
router.register("draft-anima-rituals", DraftAnimaRitualViewSet, basename="draft-anima-ritual")
router.register("applications", DraftApplicationViewSet, basename="application")
router.register(
    "draft-facet-assignments",
    DraftMotifResonanceAssociationViewSet,
    basename="draft-facet-assignment",
)

urlpatterns = [
    # Router-based URLs
    path("", include(router.urls)),
    # Standalone eligibility check
    path("can-create/", CanCreateCharacterView.as_view(), name="can-create"),
    # Form options for a species
    path(
        "form-options/<int:species_id>/",
        FormOptionsView.as_view(),
        name="form-options",
    ),
]
