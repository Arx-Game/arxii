from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.areas.constants import AreaLevel


class Area(SharedMemoryModel):
    """A spatial hierarchy node representing a named area at a specific level."""

    name = models.CharField(max_length=200)
    level = models.IntegerField(choices=AreaLevel.choices)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
    )
    realm = models.ForeignKey(
        "realms.Realm",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="areas",
    )
    description = models.TextField(blank=True)
    path = models.CharField(max_length=500, db_index=True, editable=False, default="")

    class Meta:
        verbose_name = "Area"
        verbose_name_plural = "Areas"

    def __str__(self):
        return f"{self.name} ({self.get_level_display()})"
