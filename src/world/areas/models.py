from django.core.exceptions import ValidationError
from django.db import connection, models
from django.utils import timezone
from evennia.utils.idmapper.models import SharedMemoryModel

from world.areas.constants import AreaLevel
from world.buildings.constants import PermitEligibility


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
    climate = models.ForeignKey(
        "weather.Climate",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="areas",
        help_text=(
            "Regional climate baseline (#1522). Resolves most-specific-wins down the "
            "hierarchy (see weather.services.get_effective_climate), like realm."
        ),
    )
    dominant_society = models.ForeignKey(
        "societies.Society",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="dominant_areas",
        help_text=(
            "When set, only this society's fashion is perceived in this area; "
            "otherwise all societies sharing the area's realm are relevant."
        ),
    )
    description = models.TextField(blank=True)
    color = models.CharField(
        max_length=20,
        blank=True,
        help_text=(
            "Evennia colour tag for this area in the `where` hierarchy path (e.g. '|y', "
            "'|520'). Inherited by descendants that leave their own colour blank, so a "
            "colour set on a region/house cascades down. Author-set flavour (#1463)."
        ),
    )

    # Ward-level permit configuration. Only meaningful at level WARD;
    # other levels keep the defaults and ignore them. The buildings app
    # reads these to gate construction.
    permit_eligibility = models.CharField(
        max_length=32,
        choices=PermitEligibility.choices,
        default=PermitEligibility.OPEN,
    )
    permit_cost_multiplier = models.DecimalField(
        max_digits=5,
        decimal_places=3,
        default=1,
    )
    allowed_building_kinds = models.ManyToManyField(
        "buildings.BuildingKind",
        related_name="allowed_in_wards",
        blank=True,
    )
    grid_x = models.IntegerField(
        null=True,
        blank=True,
        help_text=(
            "Position within the PARENT area's local grid (rendering/hint data only — "
            "never routing); units are parent-local cells, meaningful only among siblings."
        ),
    )
    grid_y = models.IntegerField(
        null=True,
        blank=True,
        help_text=(
            "Position within the PARENT area's local grid (rendering/hint data only — "
            "never routing); units are parent-local cells, meaningful only among siblings."
        ),
    )

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


class AreaClosure(SharedMemoryModel):
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


class AreaQuality(SharedMemoryModel):
    """Per-Area quality stat (sidecar, ADR-0010 — Area stays dependency-free).

    Quality 0-5 (3 = Ordinary). Raised by CLEANUP projects, eroded by crime
    and combat, decays/regains via weekly sweep.
    """

    area = models.OneToOneField(
        Area,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="quality",
    )
    quality = models.PositiveSmallIntegerField(default=3)
    condition_since = models.DateTimeField(default=timezone.now)

    def __str__(self) -> str:
        return f"{self.area}: quality {self.quality}"


class CleanupProjectDetails(SharedMemoryModel):
    """Per-(CLEANUP Project) details payload (#1889).

    A TIERED_PERIOD project targeting a neighborhood Area. Players contribute
    over a period; at the deadline progress is graded into a CheckOutcome tier
    via CleanupTierThreshold rows, and the tier's quality_delta bumps
    AreaQuality.
    """

    project = models.OneToOneField(
        "projects.Project",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="cleanup_details",
    )
    target_area = models.ForeignKey(
        Area,
        on_delete=models.PROTECT,
        related_name="cleanup_projects",
    )
    applied_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the quality bump was applied; NULL until the handler runs.",
    )

    def __str__(self) -> str:
        return f"Cleanup#{self.project_id}: {self.target_area}"


class CleanupTierThreshold(SharedMemoryModel):
    """A progress band on a CleanupProjectDetails that grants a CheckOutcome tier.

    Tier reached at deadline = highest min_progress row whose
    min_progress <= project.current_progress. The quality_delta field
    determines how much AreaQuality rises for this tier.
    """

    details = models.ForeignKey(
        CleanupProjectDetails,
        on_delete=models.CASCADE,
        related_name="tier_thresholds",
    )
    outcome_tier = models.ForeignKey(
        "traits.CheckOutcome",
        on_delete=models.PROTECT,
        related_name="cleanup_thresholds",
    )
    min_progress = models.PositiveIntegerField()
    quality_delta = models.PositiveSmallIntegerField(
        help_text="How much quality rises if this tier is reached.",
    )

    class Meta:
        ordering = ["-min_progress"]
        constraints = [
            models.UniqueConstraint(
                fields=["details", "outcome_tier"],
                name="uniq_cleanup_tier",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.outcome_tier} @ {self.min_progress} (+{self.quality_delta})"


def refresh_area_closure() -> None:
    """Refresh the areas_areaclosure materialized view."""
    with connection.cursor() as cursor:
        cursor.execute("REFRESH MATERIALIZED VIEW areas_areaclosure")


from world.areas.positioning.models import (  # noqa: E402,F401
    ObjectPosition,
    Position,
    PositionEdge,
)
