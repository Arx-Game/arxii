"""Models for character-to-character relationships."""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


class RelationshipCondition(SharedMemoryModel):
    """
    Conditions that can exist on a relationship.

    These represent specific states or feelings one character has toward another,
    such as "Attracted To", "Fears", "Trusts", etc. Conditions gate which
    situational modifiers (from distinctions, magic, etc.) apply during
    roll resolution.

    Examples:
    - "Attracted To" gates the Allure modifier from the Attractive distinction
    - "Fears" gates intimidation-related modifiers
    - "Trusts" gates persuasion-related modifiers
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Condition name (e.g., 'Attracted To', 'Fears', 'Trusts')",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what this condition represents",
    )
    display_order = models.PositiveIntegerField(
        default=0,
        help_text="Order for display purposes (lower values appear first)",
    )

    # Which modifiers does this condition gate?
    gates_modifiers = models.ManyToManyField(
        "mechanics.ModifierType",
        blank=True,
        related_name="gated_by_conditions",
        help_text="Modifier types that only apply when this condition exists",
    )

    class Meta:
        ordering = ["display_order", "name"]

    def __str__(self):
        return self.name
