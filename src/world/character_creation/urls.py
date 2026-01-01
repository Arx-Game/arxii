"""
Character Creation URL configuration.
"""

from django.urls import path

from world.character_creation.views import (
    AddToRosterView,
    CanCreateCharacterView,
    CharacterDraftView,
    FamilyListView,
    SpeciesListView,
    StartingAreaViewSet,
    SubmitDraftView,
)

app_name = "character_creation"

urlpatterns = [
    # Starting areas
    path(
        "starting-areas/",
        StartingAreaViewSet.as_view({"get": "list"}),
        name="starting-area-list",
    ),
    path(
        "starting-areas/<int:pk>/",
        StartingAreaViewSet.as_view({"get": "retrieve"}),
        name="starting-area-detail",
    ),
    # Species (stub)
    path("species/", SpeciesListView.as_view(), name="species-list"),
    # Families
    path("families/", FamilyListView.as_view(), name="family-list"),
    # Draft management
    path("draft/", CharacterDraftView.as_view(), name="draft"),
    path("draft/submit/", SubmitDraftView.as_view(), name="draft-submit"),
    path("draft/add-to-roster/", AddToRosterView.as_view(), name="draft-add-to-roster"),
    # Eligibility check
    path("can-create/", CanCreateCharacterView.as_view(), name="can-create"),
]
