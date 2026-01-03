from django.db import models


class Realm(models.Model):
    """Canonical realm data (e.g., Arx, Luxan) used across the project.

    Keep this minimal for now: name and description, with optional crest.
    Character creation will reference Realm via StartingArea metadata.
    """

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True, blank=True)
    description = models.TextField(blank=True)
    crest_asset = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional image/asset identifier for the realm's crest or placeholder",
    )

    class Meta:
        verbose_name = "Realm"
        verbose_name_plural = "Realms"
        ordering = ["name"]

    def __str__(self):
        return self.name
