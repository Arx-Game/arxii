"""
Roster system views.

This module is organized into logical groups:
- roster_views: Roster listing views
- entry_views: RosterEntry views and related functionality
- media_views: PlayerMedia and gallery views
- family_views: Family tree views and relationships
"""

# Import all views for backward compatibility
from world.roster.views.entry_views import RosterEntryPagination, RosterEntryViewSet
from world.roster.views.family_views import (
    FamilyMemberViewSet,
    FamilyRelationshipViewSet,
    FamilyViewSet,
)
from world.roster.views.mail_views import PlayerMailPagination, PlayerMailViewSet
from world.roster.views.media_views import PlayerMediaViewSet, TenureGalleryViewSet
from world.roster.views.roster_views import RosterViewSet
from world.roster.views.tenure_views import RosterTenureViewSet

__all__ = [
    "FamilyMemberViewSet",
    "FamilyRelationshipViewSet",
    "FamilyViewSet",
    "PlayerMailPagination",
    "PlayerMailViewSet",
    "PlayerMediaViewSet",
    "RosterEntryPagination",
    "RosterEntryViewSet",
    "RosterTenureViewSet",
    "RosterViewSet",
    "TenureGalleryViewSet",
]
