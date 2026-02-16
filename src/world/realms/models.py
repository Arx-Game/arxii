from django.db import models
from django.utils.text import slugify

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.realms.constants import RealmTheme


class Realm(NaturalKeyMixin, models.Model):
    """Canonical realm data (e.g., Arx, Luxan) used across the project.

    Keep this minimal for now: name and description, with optional crest.
    Character creation will reference Realm via StartingArea metadata.
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    crest_asset = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional image/asset identifier for the realm's crest or placeholder",
    )
    theme = models.CharField(
        max_length=20,
        choices=RealmTheme.choices,
        default=RealmTheme.DEFAULT,
        help_text="Visual theme applied in the frontend when this realm is active.",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        verbose_name = "Realm"
        verbose_name_plural = "Realms"
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def slug(self) -> str:
        """Generate slug from name on demand."""
        return slugify(self.name)
