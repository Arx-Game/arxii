"""TechniqueGrant sidecar — links a Technique to a delivery vehicle (#1732).

Authored catalog connecting a Technique to either an ItemTemplate (on-use
delivery) or a Ritual (SERVICE delivery). Exactly one vehicle must be set.
"""

from django.core.exceptions import ValidationError
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


class TechniqueGrant(SharedMemoryModel):
    """Authored link from a technique to an item or ritual delivery vehicle.

    When a character uses the linked item (via UseItemAction) or performs
    the linked ritual (via PerformRitualAction with execution_kind=SERVICE),
    the grant's technique is learned via ``learn_technique``.
    """

    technique = models.ForeignKey(
        "magic.Technique",
        on_delete=models.PROTECT,
        related_name="grants",
        help_text="The technique this grant teaches.",
    )
    item_template = models.ForeignKey(
        "items.ItemTemplate",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="technique_grants",
        help_text="Item that grants this technique on use. Mutually exclusive with ritual.",
    )
    ritual = models.ForeignKey(
        "magic.Ritual",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="technique_grants",
        help_text=(
            "Ritual that grants this technique on performance. "
            "Mutually exclusive with item_template."
        ),
    )
    acquisition_ap_cost = models.PositiveIntegerField(
        default=0,
        help_text="AP cost to learn via this grant (0 = free).",
    )
    acquisition_xp_cost = models.PositiveIntegerField(
        default=0,
        help_text="XP cost to learn via this grant (0 = free).",
    )
    verb = models.CharField(
        max_length=50,
        default="study",
        help_text="Narrative verb for the acquisition message (study, devour, consume, meditate).",
    )
    flavor_text = models.TextField(
        blank=True,
        default="",
        help_text="Optional flavor text shown on acquisition.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Technique Grant"
        verbose_name_plural = "Technique Grants"
        constraints = [
            models.UniqueConstraint(
                fields=["technique", "item_template"],
                condition=models.Q(item_template__isnull=False),
                name="unique_technique_item_grant",
            ),
            models.UniqueConstraint(
                fields=["technique", "ritual"],
                condition=models.Q(ritual__isnull=False),
                name="unique_technique_ritual_grant",
            ),
        ]

    def __str__(self) -> str:
        vehicle = self.item_template or self.ritual
        return f"{self.technique.name} via {vehicle}"

    def clean(self) -> None:
        """Enforce exactly one of item_template / ritual is set."""
        both_msg = "A TechniqueGrant must have exactly one of item_template or ritual, not both."
        neither_msg = "A TechniqueGrant must have either an item_template or a ritual."
        if self.item_template_id and self.ritual_id:
            raise ValidationError(both_msg)
        if not self.item_template_id and not self.ritual_id:
            raise ValidationError(neither_msg)
