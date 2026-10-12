"""The world map's four tables (#4242, ADR-0328).

``RegionMap`` is a region on the one world grid: an anchor cell and a width in
cells. ``RegionMapUpload`` is each generator file ever uploaded for it, kept
whole in the database (production has no persistent media disk and ADR-0237
makes the database the master copy of authored content). ``TerrainPip`` is one
10-mile square of ground and who said what it is. ``AreaFootprintPip`` is one
pip of one area's footprint; a pip's holder is the lowest area whose footprint
contains it, derived at read time and never stored.
"""

from django.db import models

from core.models import ArxSharedMemoryModel as SharedMemoryModel
from world.areas.worldmap.constants import PipSource, Terrain

ACCOUNT_DB_MODEL = "accounts.AccountDB"


class RegionMap(SharedMemoryModel):
    """A region of the world map: where it sits on the world grid and how wide it is.

    World coordinates are pips; the anchor is in cells, so a region's first pip is
    ``anchor_x * PIPS_PER_CELL``. Regions tile beside each other; seams are stitched
    by staff paint, never by the generator (ruling 7).
    """

    name = models.CharField(max_length=120, unique=True)
    area = models.ForeignKey(
        "arxii.Area",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="region_maps",
        help_text="The continent-level Area this map is the geography of, once one exists.",
    )
    anchor_x = models.IntegerField(help_text="West edge, in world cells.")
    anchor_y = models.IntegerField(help_text="North edge, in world cells.")
    width_cells = models.PositiveSmallIntegerField(
        help_text="The uploaded map is scaled to this many 100-mile cells across."
    )
    height_cells = models.PositiveSmallIntegerField(
        default=0,
        help_text="Set from the first upload's aspect ratio; 0 until a file is uploaded.",
    )
    created_by = models.ForeignKey(
        ACCOUNT_DB_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    @property
    def pip_x0(self) -> int:
        from world.areas.worldmap.constants import PIPS_PER_CELL  # noqa: PLC0415

        return self.anchor_x * PIPS_PER_CELL

    @property
    def pip_y0(self) -> int:
        from world.areas.worldmap.constants import PIPS_PER_CELL  # noqa: PLC0415

        return self.anchor_y * PIPS_PER_CELL


class RegionMapUpload(SharedMemoryModel):
    """One generator file uploaded for a region. Append-only: every file is kept,
    none is overwritten (ruling 5). ``file_bytes`` is the file gzip-compressed;
    the download view serves it decompressed under ``file_name``.
    """

    region = models.ForeignKey(RegionMap, on_delete=models.CASCADE, related_name="uploads")
    file_name = models.CharField(max_length=200)
    file_bytes = models.BinaryField(help_text="The .map file, gzip-compressed.")
    byte_size = models.PositiveIntegerField(help_text="Size of the file as uploaded.")
    generator_version = models.CharField(max_length=40, blank=True)
    source_width_px = models.PositiveIntegerField()
    source_height_px = models.PositiveIntegerField()
    uploaded_by = models.ForeignKey(
        ACCOUNT_DB_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    rasterized_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self) -> str:
        return f"{self.region} <- {self.file_name}"


class TerrainPip(SharedMemoryModel):
    """One 10-mile square of ground: its terrain, the generator's height for it,
    whether a river runs through it, and whether the generator or a staff
    member last said so. Footprints repeat the coordinates rather than point
    here, so a re-rasterize can delete and rewrite the generator's rows freely.
    """

    region = models.ForeignKey(RegionMap, on_delete=models.PROTECT, related_name="pips")
    x = models.IntegerField(help_text="World pip column (east).")
    y = models.IntegerField(help_text="World pip row (south).")
    terrain = models.CharField(max_length=16, choices=Terrain.choices)
    height = models.PositiveSmallIntegerField(
        default=0, help_text="The generator's height, 0-100; sea below 20."
    )
    has_river = models.BooleanField(default=False)
    source = models.CharField(max_length=16, choices=PipSource.choices, db_index=True)

    class Meta:
        ordering = ["y", "x"]
        constraints = [
            models.UniqueConstraint(fields=["x", "y"], name="worldmap_one_terrain_per_pip"),
        ]
        indexes = [models.Index(fields=["region", "source"], name="worldmap_pip_region_src")]

    def __str__(self) -> str:
        return f"({self.x}, {self.y}) {self.terrain}"


class AreaFootprintPip(SharedMemoryModel):
    """One pip of one area's footprint. Every tier stores its own pips (a
    county's open ground between its baronies is still the county's), and the
    containment rule (a child's pip lies in its parent's footprint) is enforced
    by ``set_footprint``, since it spans rows.
    """

    area = models.ForeignKey("arxii.Area", on_delete=models.CASCADE, related_name="footprint")
    x = models.IntegerField()
    y = models.IntegerField()

    class Meta:
        ordering = ["y", "x"]
        constraints = [
            models.UniqueConstraint(fields=["area", "x", "y"], name="worldmap_one_pip_per_area"),
        ]
        indexes = [models.Index(fields=["x", "y"], name="worldmap_footprint_xy")]

    def __str__(self) -> str:
        return f"{self.area_id} @ ({self.x}, {self.y})"
