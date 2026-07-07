"""
Roster system models.

This module is organized into logical groups:
- choices: Common choices and validation constants
- roster_core: Roster and RosterEntry models
- tenures: RosterTenure model
- applications: RosterApplication model
- settings: TenureDisplaySettings and TenureMedia models
- mail: PlayerMail model
- families: Family + the kinship graph (#2062)
"""

# Import all models for backward compatibility
from world.roster.models.applications import RosterApplication
from world.roster.models.choices import (
    ApplicationAction,
    ApplicationStatus,
    ApprovalScope,
    PlotInvolvement,
    RosterType,
    ValidationErrorCodes,
    ValidationMessages,
)
from world.roster.models.families import (
    Family,
    FamilyMembership,
    KinSlotPool,
    Kinsperson,
    ParentageEdge,
    Soul,
    SoulIncarnation,
    Union,
    UnionKind,
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
    "ApplicationAction",
    "ApplicationStatus",
    "ApprovalScope",
    "Family",
    "FamilyMembership",
    "KinSlotPool",
    "Kinsperson",
    "ParentageEdge",
    "PlayerMail",
    "PlotInvolvement",
    "Roster",
    "RosterApplication",
    "RosterEntry",
    "RosterTenure",
    "RosterType",
    "Soul",
    "SoulIncarnation",
    "TenureDisplaySettings",
    "TenureGallery",
    "TenureMedia",
    "Union",
    "UnionKind",
    "ValidationErrorCodes",
    "ValidationMessages",
]
