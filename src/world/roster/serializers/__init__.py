"""
Roster system serializers.

This module is organized into logical groups:
- characters: Character-related serializers
- media: Media and gallery serializers
- tenures: RosterTenure serializers
- roster_core: Roster and RosterEntry serializers
- applications: RosterApplication serializers
- mail: PlayerMail serializers
- families: Family tree serializers
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
from world.roster.serializers.families import (
    FamilyMemberSerializer,
    FamilySerializer,
    FamilyTreeSerializer,
)
from world.roster.serializers.mail import PlayerMailSerializer
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
from world.roster.serializers.tenures import (
    RosterTenureLookupSerializer,
    RosterTenureSerializer,
)

__all__ = [
    # Media serializers
    "ArtistSerializer",
    # Character serializers
    "CharacterGallerySerializer",
    "CharacterSerializer",
    # Family serializers
    "FamilyMemberSerializer",
    "FamilySerializer",
    "FamilyTreeSerializer",
    "MyRosterEntrySerializer",
    # Mail serializers
    "PlayerMailSerializer",
    "PlayerMediaSerializer",
    "RosterApplicationApprovalSerializer",
    "RosterApplicationCreateSerializer",
    "RosterApplicationDetailSerializer",
    "RosterApplicationEligibilitySerializer",
    # Application serializers
    "RosterApplicationSerializer",
    "RosterEntryListSerializer",
    # Roster core serializers
    "RosterEntrySerializer",
    "RosterListSerializer",
    "RosterTenureLookupSerializer",
    # Tenure serializers
    "RosterTenureSerializer",
    "TenureGallerySerializer",
    "TenureMediaSerializer",
]
