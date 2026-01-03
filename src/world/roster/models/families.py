"""
Family model for character lineage.

Simple model to track which characters belong to which family.
Staff can change a character's family at any time (e.g., for secret heritage reveals).

TODO: Add relationship tracking between family members
TODO: Add domain/wargame mechanics for noble houses
"""

from django.db import models
from evennia.accounts.models import AccountDB
from evennia.utils.idmapper.models import SharedMemoryModel


class Family(SharedMemoryModel):
    """
    A family/house that characters can belong to.

    Uses SharedMemoryModel for performance since families are accessed
    frequently but changed rarely.
    """

    class FamilyType(models.TextChoices):
        COMMONER = "commoner", "Commoner"
        NOBLE = "noble", "Noble"

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Family/house name",
    )
    family_type = models.CharField(
        max_length=20,
        choices=FamilyType.choices,
        default=FamilyType.COMMONER,
        help_text="Whether this is a noble house or commoner family",
    )
    description = models.TextField(
        blank=True,
        help_text="Brief description of the family",
    )
    is_playable = models.BooleanField(
        default=True,
        help_text="Whether players can select this family in character creation",
    )
    # True if created during character generation (commoner only)
    created_by_cg = models.BooleanField(
        default=False,
        help_text="True if created during character generation (commoner only)",
    )

    # Record the account who created this family (helpful for provenance/contact)
    created_by = models.ForeignKey(
        AccountDB,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_families",
        help_text="Account that created this family (staff or player-created commoner)",
    )

    # Canonical origin realm (realms.Realm) rather than pointing at character_creation
    origin_realm = models.ForeignKey(
        "realms.Realm",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="families",
        help_text=(
            "Canonical realm this family is associated with; used to filter in character creation"
        ),
    )

    # TODO: domain = models.ForeignKey('domains.Domain', ...) - for noble house mechanics
    # TODO: prestige = models.IntegerField(default=0) - for wargame mechanics

    class Meta:
        verbose_name = "Family"
        verbose_name_plural = "Families"
        ordering = ["family_type", "name"]

    def __str__(self):
        return self.name
