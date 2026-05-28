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

    class Meta:
        abstract = True
