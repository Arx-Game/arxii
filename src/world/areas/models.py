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
    """Transitive closure of the area hierarchy.

    Stores every ancestor-descendant pair with depth so that ancestry and
    subtree queries are simple indexed lookups instead of recursive walks.
    Refreshed automatically when an Area is saved or deleted.
    """

    ancestor = models.ForeignKey(Area, on_delete=models.CASCADE, related_name="+")
    descendant = models.ForeignKey(Area, on_delete=models.CASCADE, related_name="+")
    depth = models.IntegerField()

    class Meta:
        indexes = [
            models.Index(fields=["ancestor"]),
            models.Index(fields=["descendant"]),
            models.Index(fields=["ancestor", "descendant"]),
        ]

    def __str__(self):
        return f"{self.ancestor_id} -> {self.descendant_id} (depth {self.depth})"


def refresh_area_closure() -> None:
    """Rebuild the AreaClosure table from the current parent FK chain.

    On Postgres, uses a recursive CTE for a fast single-statement rebuild.
    On other backends (e.g. SQLite in tests), uses Python iteration.
    """
    vendor = connection.vendor
    if vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM areas_areaclosure")
            cursor.execute("""
                INSERT INTO areas_areaclosure (ancestor_id, descendant_id, depth)
                WITH RECURSIVE closure AS (
                    SELECT id AS ancestor_id, id AS descendant_id, 0 AS depth
                    FROM areas_area
                    UNION ALL
                    SELECT c.ancestor_id, a.id AS descendant_id, c.depth + 1
                    FROM closure c
                    JOIN areas_area a ON a.parent_id = c.descendant_id
                )
                SELECT ancestor_id, descendant_id, depth FROM closure
            """)
    else:
        _refresh_area_closure_python()


def _refresh_area_closure_python() -> None:
    """Rebuild AreaClosure using Python iteration (for SQLite compatibility)."""
    AreaClosure.objects.all().delete()

    areas = {a.pk: a for a in Area.objects.all()}
    rows = []
    for area in areas.values():
        depth = 0
        node = area
        while node is not None:
            rows.append(AreaClosure(ancestor_id=node.pk, descendant_id=area.pk, depth=depth))
            node = areas.get(node.parent_id)
            depth += 1

    AreaClosure.objects.bulk_create(rows)
