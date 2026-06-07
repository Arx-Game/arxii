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


class RoleArchetype(models.TextChoices):
    """Foundational combat archetype for covenant roles.

    At early levels players pick from these three. Specialized sub-roles
    unlock later within each archetype.
    """

    SWORD = "sword", "Sword"  # Offense
    SHIELD = "shield", "Shield"  # Defense
    CROWN = "crown", "Crown"  # Support


class BattleBinding(models.TextChoices):
    """How a Battle covenant is bound to its cause (Slice E).

    STANDING covenants (a military unit or a state's banner-call) can rise
    again after standing down. CAMPAIGN covenants are bound to a single
    event and dissolve when it concludes.
    """

    STANDING = "standing", "Standing (unit or banner — can rise again)"
    CAMPAIGN = "campaign", "Campaign (one-time event — dissolves when done)"
