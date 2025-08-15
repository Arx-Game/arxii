"""
Roster system serializers.

This module is organized into logical groups:
- characters: Character-related serializers
- media: Media and gallery serializers
- tenures: RosterTenure serializers
- roster_core: Roster and RosterEntry serializers
- applications: RosterApplication serializers
"""

# Import all serializers for backward compatibility
from world.roster.serializers.applications import (
    RosterApplicationApprovalSerializer,
    RosterApplicationCreateSerializer,
    RosterApplicationDetailSerializer,
    RosterApplicationEligibilitySerializer,
    RosterApplicationSerializer,
)
from world.roster.serializers.characters import (
    CharacterGallerySerializer,
    CharacterSerializer,
)
from world.roster.serializers.media import (
    ArtistSerializer,
    PlayerMediaSerializer,
    TenureGallerySerializer,
    TenureMediaSerializer,
)
from world.roster.serializers.roster_core import (
    MyRosterEntrySerializer,
    RosterEntryListSerializer,
    RosterEntrySerializer,
    RosterListSerializer,
)
from world.roster.serializers.tenures import RosterTenureSerializer

__all__ = [
    # Character serializers
    "CharacterGallerySerializer",
    "CharacterSerializer",
    # Media serializers
    "ArtistSerializer",
    "PlayerMediaSerializer",
    "TenureGallerySerializer",
    "TenureMediaSerializer",
    # Tenure serializers
    "RosterTenureSerializer",
    # Roster core serializers
    "RosterEntrySerializer",
    "MyRosterEntrySerializer",
    "RosterEntryListSerializer",
    "RosterListSerializer",
    # Application serializers
    "RosterApplicationSerializer",
    "RosterApplicationCreateSerializer",
    "RosterApplicationDetailSerializer",
    "RosterApplicationApprovalSerializer",
    "RosterApplicationEligibilitySerializer",
]
