"""General material stock models (#2540 slice 2): buckets, pools, org stocks.

Aggregate (never-instanced) material value, keyed to a ``MaterialCategory``. These
three models started as gem-only "common gem" buckets (Build 0b) and are generalized
here so any bulk material — not just gems — can share the same
stock/pool/org-stock shape: a crafter's per-category ``MaterialBucket``, a mine or
other income stream's uncollected ``StreamMaterialPool``, and an org's collected
``OrgMaterialStock``. Genuinely gem-specific models (``GemGrade``, ``GemDetails``,
``GemInstanceDetails``, ``PendingRareFind``, ``Adornment``) stay in
``world.items.gems.models``.

All models set ``Meta.app_label = "arxii"`` (the single collapsed app, #2906).
"""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

_MATERIAL_CATEGORY_FK = "arxii.MaterialCategory"


class MaterialBucket(SharedMemoryModel):
    """A crafter's stock of bulk material as an aggregate value, per category.

    Bulk material is never instanced — it lives as a per-category value integer
    that mining/production credits and bulk crafting spends ("slap 20 semiprecious
    on the table, don't care which"). Keyed to a CharacterSheet + a
    ``MaterialCategory``. This is the type-blind bulk source; specific-type demand
    still uses real instances.
    """

    character_sheet = models.ForeignKey(
        "arxii.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="material_buckets",
    )
    material_category = models.ForeignKey(
        _MATERIAL_CATEGORY_FK,
        on_delete=models.PROTECT,
        related_name="material_buckets",
        help_text="The material category this value is denominated in.",
    )
    value = models.PositiveIntegerField(
        default=0,
        help_text="Aggregate material value held, in coppers.",
    )

    class Meta:
        app_label = "arxii"
        constraints = [
            models.UniqueConstraint(
                fields=["character_sheet", "material_category"],
                name="items_materialbucket_sheet_category_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"sheet {self.character_sheet_id} {self.material_category}: {self.value}"


class StreamMaterialPool(SharedMemoryModel):
    """Per-category uncollected material value amassed by an income stream.

    The material analogue of ``OrgIncomeStream.uncollected_pool``: a production
    cycle (mining or otherwise) accrues bulk value here, and it rides the *same*
    active collection dispatch (graft/loss) into the house's collected material
    stock. Keyed to the stream + ``MaterialCategory``.
    """

    income_stream = models.ForeignKey(
        "arxii.OrgIncomeStream",
        on_delete=models.CASCADE,
        related_name="material_pools",
    )
    material_category = models.ForeignKey(
        _MATERIAL_CATEGORY_FK,
        on_delete=models.PROTECT,
        related_name="+",
    )
    uncollected_value = models.PositiveBigIntegerField(
        default=0,
        help_text="Material value awaiting collection. No cap — a hoarded pool is outcome risk.",
    )

    class Meta:
        app_label = "arxii"
        constraints = [
            models.UniqueConstraint(
                fields=["income_stream", "material_category"],
                name="items_streammaterialpool_stream_category_unique",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"stream {self.income_stream_id} {self.material_category}: "
            f"{self.uncollected_value} uncollected"
        )


class OrgMaterialStock(SharedMemoryModel):
    """An organization's *collected* material value, per category.

    The house-level shared stock that members craft from (the B ownership model).
    Production accrues into per-stream ``StreamMaterialPool``s; an active
    ``collect_org_income`` dispatch delivers the net (after the same band + graft
    the coin rides) here.
    """

    organization = models.ForeignKey(
        "arxii.Organization",
        on_delete=models.CASCADE,
        related_name="material_stocks",
    )
    material_category = models.ForeignKey(
        _MATERIAL_CATEGORY_FK,
        on_delete=models.PROTECT,
        related_name="+",
    )
    value = models.PositiveBigIntegerField(
        default=0,
        help_text="Collected material value the house holds, in coppers.",
    )

    class Meta:
        app_label = "arxii"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "material_category"],
                name="items_orgmaterialstock_org_category_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"org {self.organization_id} {self.material_category}: {self.value}"
