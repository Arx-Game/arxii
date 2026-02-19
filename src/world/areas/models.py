from django.core.exceptions import ValidationError
from django.db import models
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
    mat_path = models.CharField(max_length=500, db_index=True, editable=False, default="")

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

    def build_mat_path(self):
        """Build materialized path from ancestor PKs, root to parent."""
        ancestors = []
        node = self.parent
        while node is not None:
            ancestors.append(str(node.pk))
            node = node.parent
        return "/".join(reversed(ancestors))

    def save(self, *args, **kwargs):
        self.full_clean()
        self.mat_path = self.build_mat_path()
        super().save(*args, **kwargs)
