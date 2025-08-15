"""
Roster system views.

This module is organized into logical groups:
- roster_views: Roster listing views
- entry_views: RosterEntry views and related functionality
- media_views: PlayerMedia and gallery views
"""

# Import all views for backward compatibility
from world.roster.views.entry_views import RosterEntryPagination, RosterEntryViewSet
from world.roster.views.mail_views import PlayerMailPagination, PlayerMailViewSet
from world.roster.views.media_views import PlayerMediaViewSet
from world.roster.views.roster_views import RosterViewSet
from world.roster.views.tenure_views import RosterTenureViewSet

__all__ = [
    "RosterEntryPagination",
    "RosterEntryViewSet",
    "RosterViewSet",
    "PlayerMediaViewSet",
    "PlayerMailPagination",
    "PlayerMailViewSet",
    "RosterTenureViewSet",
]
