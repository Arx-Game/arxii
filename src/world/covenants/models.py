"""Models for the covenants system.

Covenants are magically-empowered oaths — blood rituals that bind participants
to shared roles and goals. This app owns role definitions and their mechanical
properties (like combat speed rank). The full covenant lifecycle (formation,
membership, progression) is future work.
"""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.covenants.constants import CovenantType, RoleArchetype
from world.items.constants import GearArchetype


class CovenantRole(SharedMemoryModel):
    """A role that a character can hold within a covenant.

    Lookup table — staff-authored, cached via SharedMemoryModel.
    Different covenant types may have different role sets; the
    covenant_type field scopes which roles are available.

    Combat reads ``speed_rank`` directly from this model during resolution
    order calculation.
    """

    name = models.CharField(max_length=60, help_text="Display name, e.g. 'Vanguard'.")
    slug = models.SlugField(
        max_length=60,
        unique=True,
        help_text="Stable identifier for code references, e.g. 'vanguard'.",
    )
    covenant_type = models.CharField(
        max_length=20,
        choices=CovenantType.choices,
        default=CovenantType.DURANCE,
        help_text="Which covenant type this role belongs to.",
    )
    archetype = models.CharField(
        max_length=20,
        choices=RoleArchetype.choices,
        help_text="Foundational archetype: Sword (offense), Shield (defense), Crown (support).",
    )
    speed_rank = models.PositiveIntegerField(
        help_text="Combat resolution order. Lower is faster (1 = fastest).",
    )
    description = models.TextField(
        blank=True,
        help_text="Player-facing description of the role's identity and combat style.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["covenant_type", "name"],
                name="unique_role_name_per_covenant_type",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_covenant_type_display()})"


class GearArchetypeCompatibility(SharedMemoryModel):
    """Existence-only join: which roles are compatible with which archetypes.

    Spec D §4.4. Row present = role bonuses add to mundane gear stats on
    that archetype. Row absent = incompatible (max(role, gear) per slot).
    """

    covenant_role = models.ForeignKey(
        "covenants.CovenantRole",
        on_delete=models.CASCADE,
        related_name="gear_compatibilities",
    )
    gear_archetype = models.CharField(
        max_length=20,
        choices=GearArchetype.choices,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["covenant_role", "gear_archetype"],
                name="covenants_unique_role_archetype_compat",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.covenant_role.name} compatible with {self.get_gear_archetype_display()}"
