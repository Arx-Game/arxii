from django.db import models
from django.utils.text import slugify
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.contributors.models import CreditedContent
from world.realms.constants import RealmTheme


class Realm(NaturalKeyMixin, CreditedContent, SharedMemoryModel):
    """Canonical realm data (e.g., Arx, Luxan) used across the project.

    Keep this minimal for now: name and description, with optional crest.
    Character creation will reference Realm via StartingArea metadata.
    """

    name = models.CharField(max_length=100, unique=True)
    formal_name = models.CharField(
        max_length=150,
        blank=True,
        help_text="The long name the realm page shows under the title (#3725), e.g. "
        "'The Umbral Empire'. Blank shows nothing.",
    )
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


class RealmTestamentSection(NaturalKeyMixin, CreditedContent, SharedMemoryModel):
    """One movement of a realm's testament, the pitch the realm page opens on (#3725).

    A testament is authored prose in movements; each movement ends on its motto line,
    rendered in the display face under the body. Three per realm today. Credited
    content (ADR-0201): the prose is the reviewer's and lives only here (ADR-0238).
    """

    realm = models.ForeignKey(
        Realm,
        on_delete=models.CASCADE,
        related_name="testament_sections",
        help_text="The realm this movement belongs to.",
    )
    sort_order = models.PositiveSmallIntegerField(
        help_text="Position of this movement in the testament, from 1.",
    )
    body = models.TextField(
        help_text="The movement's paragraphs; blank lines separate paragraphs.",
    )
    motto = models.CharField(
        max_length=200,
        blank=True,
        help_text="The line the movement ends on, shown in the display face. Blank shows nothing.",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["realm", "sort_order"]

    class Meta:
        verbose_name = "Realm testament section"
        verbose_name_plural = "Realm testament sections"
        ordering = ["realm", "sort_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["realm", "sort_order"], name="realm_testament_section_order"
            ),
        ]

    def __str__(self):
        return f"{self.realm.name} testament, movement {self.sort_order}"
