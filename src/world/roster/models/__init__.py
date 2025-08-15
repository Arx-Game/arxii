"""
Roster system models.

This module is organized into logical groups:
- choices: Common choices and validation constants
- roster_core: Roster and RosterEntry models
- tenures: RosterTenure model
- applications: RosterApplication model
- settings: TenureDisplaySettings and TenureMedia models
- mail: PlayerMail model
"""

# Import all models for backward compatibility
from world.roster.models.applications import RosterApplication
from world.roster.models.choices import (
    ApplicationStatus,
    ApprovalScope,
    PlotInvolvement,
    RosterType,
    ValidationErrorCodes,
    ValidationMessages,
)
from world.roster.models.mail import PlayerMail
from world.roster.models.roster_core import Roster, RosterEntry
from world.roster.models.settings import (
    TenureDisplaySettings,
    TenureGallery,
    TenureMedia,
)
from world.roster.models.tenures import RosterTenure

__all__ = [
    # Choices and constants
    "ApplicationStatus",
    "ApprovalScope",
    "PlotInvolvement",
    "RosterType",
    "ValidationErrorCodes",
    "ValidationMessages",
    # Core models
    "Roster",
    "RosterEntry",
    "RosterTenure",
    "RosterApplication",
    "TenureDisplaySettings",
    "TenureGallery",
    "TenureMedia",
    "PlayerMail",
]
