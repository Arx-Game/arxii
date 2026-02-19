from django.core.exceptions import ValidationError
from django.db import connection, models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.areas.constants import AreaLevel


class Area(SharedMemoryModel):
    """A spatial hierarchy node representing a named area at a specific level."""

    name = models.CharField(max_length=200)
    level = models.IntegerField(choices=AreaLevel.choices, db_index=True)
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

    class Meta:
        verbose_name = "Area"
        verbose_name_plural = "Areas"

    def __str__(self):
        return f"{self.name} ({self.get_level_display()})"

    def clean(self):
        if self.parent is None:
            return

        if self.level >= self.parent.level:
            msg = (
                f"A {self.get_level_display()} (level {self.level}) "
                f"cannot be inside a {self.parent.get_level_display()} "
                f"(level {self.parent.level})."
            )
            raise ValidationError(msg)

        seen = {self.pk}
        node = self.parent
        while node is not None:
            if node.pk in seen:
                msg = "Circular parent chain detected."
                raise ValidationError(msg)
            seen.add(node.pk)
            node = node.parent

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        refresh_area_closure()

    def delete(self, *args, **kwargs):
        result = super().delete(*args, **kwargs)
        refresh_area_closure()
        return result


class AreaClosure(models.Model):
    """Read-only model backed by a Postgres materialized view.

    Stores the transitive closure of the area hierarchy: every
    ancestor-descendant pair with depth.  Refreshed automatically
    when an Area is saved or deleted.
    """

    ancestor = models.ForeignKey(Area, on_delete=models.DO_NOTHING, related_name="+")
    descendant = models.ForeignKey(Area, on_delete=models.DO_NOTHING, related_name="+")
    depth = models.IntegerField()

    class Meta:
        managed = False
        db_table = "areas_areaclosure"

    def __str__(self):
        return f"{self.ancestor_id} -> {self.descendant_id} (depth {self.depth})"


def refresh_area_closure() -> None:
    """Refresh the areas_areaclosure materialized view."""
    with connection.cursor() as cursor:
        cursor.execute("REFRESH MATERIALIZED VIEW areas_areaclosure")
