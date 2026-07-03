"""Constants for the covenants system."""

from django.db import models

# Name of the OrganizationType row used for Covenant-backed Organizations.
# `Covenant.save()` uses `get_or_create` keyed on this name to bootstrap the
# row on first use, so no fixture loading is required.
COVENANT_ORG_TYPE_NAME = "covenant"


class CovenantType(models.TextChoices):
    """The type of magically-empowered oath."""

    DURANCE = "durance", "Covenant of the Durance"
    BATTLE = "battle", "Covenant of Battle"
    COURT = "court", "Covenant of the Court"


class RoleArchetype(models.TextChoices):
    """Foundational combat archetype for covenant roles.

    At early levels players pick from these three. Specialized sub-roles
    unlock later within each archetype.
    """

    SWORD = "sword", "Sword"  # Offense
    SHIELD = "shield", "Shield"  # Defense
    CROWN = "crown", "Crown"  # Support


class CommandTier(models.TextChoices):
    """Battle-command hierarchy tier for a CovenantRole (#1710).

    Meaningful only for CovenantType.BATTLE roles — see CovenantRole.clean().
    """

    NONE = "none", "No command tier"
    SUBORDINATE = "subordinate", "Subordinate Commander"
    SUPREME = "supreme", "Supreme Commander"


class BattleBinding(models.TextChoices):
    """How a Battle covenant is bound to its cause (Slice E).

    STANDING covenants (a military unit or a state's banner-call) can rise
    again after standing down. CAMPAIGN covenants are bound to a single
    event and dissolve when it concludes.
    """

    STANDING = "standing", "Standing (unit or banner — can rise again)"
    CAMPAIGN = "campaign", "Campaign (one-time event — dissolves when done)"


# Default rank names created during covenant formation.
DEFAULT_FOUNDER_RANK_NAME = "Founder"
DEFAULT_MEMBER_RANK_NAME = "Member"


class MentorBondAdjusted(models.TextChoices):
    """Which party of a Mentor's Vow the bond reshapes."""

    MENTOR = "mentor", "Mentor"
    SIDEKICK = "sidekick", "Sidekick"


MENTOR_BOND_BAND_WIDTH = 2
MENTOR_BOND_ADJACENCY_OFFSET = 1
MENTOR_BOND_MAX_SIDEKICKS: int | None = None
