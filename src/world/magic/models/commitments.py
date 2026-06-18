from django.db import models


class CommittingDeclaration(models.Model):
    """Player-declared cost commitments attached to an action declaration.

    Concrete declarations (clash + scene-action) inherit this mixin so scalar
    cost levers are defined in one place. List-shaped commitments
    (thread pulls) live on their own related models.
    """

    strain_commitment = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Extra anima the player commits beyond base cost. "
            "Bounded by available anima at resolution time."
        ),
    )
    fury_commitment = models.ForeignKey(
        "magic.FuryTier",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Declared Fury tier for this action (null = no fury).",
    )
    fury_anchor = models.ForeignKey(
        "character_sheets.CharacterSheet",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Harmed entity the rage answers to; bond strength caps the tier.",
    )

    class Meta:
        abstract = True
