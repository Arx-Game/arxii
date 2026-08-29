"""
Roster system views.

This module is organized into logical groups:
- roster_views: Roster listing views
- entry_views: RosterEntry views and related functionality
- media_views: Media and gallery views
- family_views: Family tree views and relationships
"""

# Import all views for backward compatibility
from world.roster.views.application_views import (
    RosterApplicationPagination,
    RosterApplicationViewSet,
)
from world.roster.views.entry_views import RosterEntryPagination, RosterEntryViewSet
from world.roster.views.family_views import (
    CharacterKinTreeView,
    FamilyViewSet,
    KinRelationshipView,
)
from world.roster.views.invite_views import GameInviteViewSet
from world.roster.views.mail_views import PlayerMailPagination, PlayerMailViewSet
from world.roster.views.media_views import MediaViewSet, TenureGalleryViewSet
from world.roster.views.npc_preset_views import NPCStatlinePresetViewSet
from world.roster.views.roster_views import RosterViewSet
from world.roster.views.tenure_views import RosterTenureViewSet

__all__ = [
    "CharacterKinTreeView",
    "FamilyViewSet",
    "GameInviteViewSet",
    "KinRelationshipView",
    "MediaViewSet",
    "NPCStatlinePresetViewSet",
    "PlayerMailPagination",
    "PlayerMailViewSet",
    "RosterApplicationPagination",
    "RosterApplicationViewSet",
    "RosterEntryPagination",
    "RosterEntryViewSet",
    "RosterTenureViewSet",
    "RosterViewSet",
    "TenureGalleryViewSet",
]
