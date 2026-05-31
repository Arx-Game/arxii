"""Constants for the covenants system."""

from django.db import models

from world.societies.constants import OrganizationKind

# The OrganizationKind value Covenants register as.
COVENANT_ORG_KIND = OrganizationKind.COVENANT


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
