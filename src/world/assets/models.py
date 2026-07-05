"""NPCAsset — a class-1 Functionary promoted to a named, privately-owned NPC (#1872)."""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.assets.constants import AssetRoleContext, AssetStatus


class NPCAsset(SharedMemoryModel):
    """A promoted class-1 Functionary, privately owned by the PC who cultivated it.

    ``promoter_persona``/``asset_persona`` is the same persona pair
    ``world.npc_services.models.NPCStanding`` keys on — ongoing affection is
    read through that existing model (no duplicate ``standing`` field here);
    the next real interaction with ``asset_persona`` creates the
    ``NPCStanding`` row automatically via the existing
    ``start_interaction``/``end_interaction`` machinery.
    """

    promoter_persona = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.PROTECT,
        related_name="promoted_assets",
        help_text="The PC's persona who cultivated this asset.",
    )
    asset_persona = models.OneToOneField(
        "scenes.Persona",
        on_delete=models.PROTECT,
        related_name="asset_promotion",
        help_text="The promoted NPC's own persona — private to one promoter.",
    )
    role_context = models.CharField(
        max_length=20,
        choices=AssetRoleContext.choices,
        help_text="What kind of relationship this asset serves.",
    )
    source_functionary = models.ForeignKey(
        "npc_services.Functionary",
        on_delete=models.PROTECT,
        related_name="promotions",
        help_text="The class-1 placement this asset was promoted from.",
    )
    status = models.CharField(
        max_length=20,
        choices=AssetStatus.choices,
        default=AssetStatus.ACTIVE,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["promoter_persona", "source_functionary"],
                name="unique_npcasset_promoter_functionary",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.asset_persona} ({self.role_context}, owned by {self.promoter_persona})"
