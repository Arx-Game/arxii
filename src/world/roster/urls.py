"""
URL patterns for the roster system API.
"""

from django.urls import path
from rest_framework.routers import DefaultRouter

from world.gm.views import LookingForTableToggleView
from world.roster.views import (
    CharacterKinTreeView,
    FamilyViewSet,
    GameInviteViewSet,
    KinRelationshipView,
    MediaViewSet,
    NPCStatlinePresetViewSet,
    PlayerMailViewSet,
    RosterApplicationViewSet,
    RosterEntryViewSet,
    RosterTenureViewSet,
    RosterViewSet,
    TenureGalleryViewSet,
)
from world.roster.views.settings_views import VisibilitySettingsView

app_name = "roster"

router = DefaultRouter()
router.register("applications", RosterApplicationViewSet, basename="applications")
router.register("rosters", RosterViewSet, basename="rosters")
router.register("entries", RosterEntryViewSet, basename="entries")
router.register("families", FamilyViewSet, basename="families")
router.register("invites", GameInviteViewSet, basename="gameinvite")
router.register("media", MediaViewSet, basename="media")
router.register("mail", PlayerMailViewSet, basename="mail")
router.register("tenures", RosterTenureViewSet, basename="tenures")
router.register("galleries", TenureGalleryViewSet, basename="galleries")
router.register("npc-presets", NPCStatlinePresetViewSet, basename="npc-presets")

urlpatterns = [
    path(
        "visibility-settings/",
        VisibilitySettingsView.as_view(),
        name="visibility-settings",
    ),
    path(
        "looking-for-table/",
        LookingForTableToggleView.as_view(),
        name="looking-for-table-toggle",
    ),
    path(
        "kin/tree/<int:character_id>/",
        CharacterKinTreeView.as_view(),
        name="kin-tree",
    ),
    path(
        "kin/relationship/",
        KinRelationshipView.as_view(),
        name="kin-relationship",
    ),
    *router.urls,
]
