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
- npc_presets: NPCStatlinePreset + its trait/skill lines (#3427)
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
    FamilyKind,
    FamilyMembership,
    KinSlotPool,
    Kinsperson,
    KinspersonTraitValue,
    ParentageEdge,
    Soul,
    SoulIncarnation,
    Union,
    UnionKind,
)
from world.roster.models.invites import GameInvite, InviteStatus
from world.roster.models.mail import PlayerMail
from world.roster.models.npc_presets import (
    NPCPresetSkillLine,
    NPCPresetTraitLine,
    NPCStatlinePreset,
)
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
    "FamilyKind",
    "FamilyMembership",
    "GameInvite",
    "InviteStatus",
    "KinSlotPool",
    "Kinsperson",
    "KinspersonTraitValue",
    "NPCPresetSkillLine",
    "NPCPresetTraitLine",
    "NPCStatlinePreset",
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
