"""NPCAsset — a class-1 Functionary promoted to a named, privately-owned NPC (#1872).

CG-granted assets (#1906) are a second acquisition channel: a starting
NPCAsset granted by a Distinction at character creation, with no cultivation
check or room placement required.
"""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.assets.constants import AssetAcquisitionSource, AssetRoleContext, AssetStatus


class NPCAsset(SharedMemoryModel):
    """A promoted class-1 Functionary or CG-granted starting asset, privately
    owned by the PC who cultivated or was granted it.

    ``promoter_persona``/``asset_persona`` is the same persona pair
    ``world.npc_services.models.NPCStanding`` keys on — ongoing affection is
    read through that existing model (no duplicate ``standing`` field here);
    the next real interaction with ``asset_persona`` creates the
    ``NPCStanding`` row automatically via the existing
    ``start_interaction``/``end_interaction`` machinery (runtime-promoted
    assets). CG-granted assets (#1906) seed an ``NPCStanding`` row at grant
    time with the authored starting affection.

    ``acquisition_source`` distinguishes the two channels: PROMOTION (runtime,
    via ``source_functionary``) vs DISTINCTION_GRANT (CG, via
    ``source_distinction_grant``). Exactly one of the two source FKs is set
    per asset — enforced by the ``source_functionary`` / ``source_distinction_grant``
    nullability (PROMOTION sets functionary, DISTINCTION_GRANT sets grant).
    """

    promoter_persona = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.PROTECT,
        related_name="promoted_assets",
        help_text="The PC's persona who cultivated or was granted this asset.",
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
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="promotions",
        help_text=(
            "The class-1 placement this asset was promoted from (runtime path). "
            "NULL for CG-granted assets (acquisition_source=DISTINCTION_GRANT)."
        ),
    )
    acquisition_source = models.CharField(
        max_length=20,
        choices=AssetAcquisitionSource.choices,
        default=AssetAcquisitionSource.PROMOTION,
        help_text="How this asset was acquired: PROMOTION (runtime) or DISTINCTION_GRANT (CG).",
    )
    source_distinction_grant = models.ForeignKey(
        "assets.DistinctionAssetGrant",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="granted_assets",
        help_text=(
            "The DistinctionAssetGrant that created this asset (CG path). "
            "NULL for runtime-promoted assets. Serves as the idempotency key: "
            "one CG asset per (promoter, grant) at the DB level."
        ),
    )
    status = models.CharField(
        max_length=20,
        choices=AssetStatus.choices,
        default=AssetStatus.ACTIVE,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # Runtime path: one promoted asset per (promoter, functionary).
            # NULL source_functionary (CG grants) are exempt — Postgres treats
            # NULLs as not-equal, so this constraint does not guard against
            # duplicate CG grants; the partial constraint below does that.
            models.UniqueConstraint(
                fields=["promoter_persona", "source_functionary"],
                name="unique_npcasset_promoter_functionary",
            ),
            # CG path: one granted asset per (promoter, DistinctionAssetGrant).
            # Partial (condition on non-null) because runtime-promoted assets
            # have this NULL and should not collide.
            models.UniqueConstraint(
                fields=["promoter_persona", "source_distinction_grant"],
                condition=models.Q(source_distinction_grant__isnull=False),
                name="unique_npcasset_promoter_distinction_grant",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.asset_persona} ({self.role_context}, owned by {self.promoter_persona})"


class DistinctionAssetGrant(SharedMemoryModel):
    """Staff-authored sidecar mapping a Distinction to a starting NPCAsset
    granted at character creation (#1906).

    Mirrors ``DistinctionResonanceGrant``'s sidecar shape (the resonance-currency
    sibling, ``world.magic.models.grants``), but grants an NPC asset instead of
    resonance. Lives in ``world.assets`` (per ADR-0010: the sidecar lives in
    the app that owns the general primitive — here ``NPCAsset``, not
    ``magic.Resonance``).

    At CG finalization, ``reconcile_distinction_asset_grants`` reads these rows
    for each ``CharacterDistinction`` and creates one ``NPCAsset`` per grant —
    no cultivation check, no room placement. The ``asset_display_name`` is used
    as both the spawned character's key and the persona name.
    """

    distinction = models.ForeignKey(
        "distinctions.Distinction",
        on_delete=models.CASCADE,
        related_name="asset_grants",
        help_text="The Distinction that grants this asset at character creation.",
    )
    npc_role = models.ForeignKey(
        "npc_services.NPCRole",
        on_delete=models.PROTECT,
        related_name="distinction_grants",
        help_text="The NPCRole the granted asset's persona is assigned to.",
    )
    role_context = models.CharField(
        max_length=20,
        choices=AssetRoleContext.choices,
        help_text="What kind of relationship this asset serves (informant/contact/personal_favor).",
    )
    starting_affection = models.IntegerField(
        default=0,
        help_text="Initial NPCStanding.affection seeded at grant time.",
    )
    asset_display_name = models.CharField(
        max_length=200,
        help_text=(
            "Name used as the spawned character's key + persona name. "
            "Two PCs taking the same Distinction will each spawn an NPC with "
            "this name — lookups go through the NPCAsset FK/persona, not by key."
        ),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["distinction", "npc_role", "role_context"],
                name="unique_distinction_asset_grant",
            ),
        ]
        ordering = ["distinction_id", "npc_role_id"]
        verbose_name = "Distinction Asset Grant"
        verbose_name_plural = "Distinction Asset Grants"

    def __str__(self) -> str:
        return f"{self.distinction} grants {self.asset_display_name} ({self.role_context})"


class AssetTaskIntelDetails(SharedMemoryModel):
    """Per-kind details for ASSET_TASK_INTEL offers (#1905).

    Mirrors the existing per-kind details pattern (PermitOfferDetails,
    LoanOfferDetails, CourtGrantOfferDetails) — a 1:1 reverse from
    NPCServiceOffer carrying the kind-specific parameters. For intel tasks,
    the parameter is the Clue granted on a successful check.
    """

    offer = models.OneToOneField(
        "npc_services.NPCServiceOffer",
        on_delete=models.CASCADE,
        related_name="asset_task_intel_details",
    )
    clue = models.ForeignKey(
        "clues.Clue",
        on_delete=models.PROTECT,
        related_name="asset_task_offers",
        help_text="The clue granted on a successful intel task.",
    )

    class Meta:
        verbose_name = "Asset Task Intel Details"
        verbose_name_plural = "Asset Task Intel Details"

    def __str__(self) -> str:
        return f"Intel task: {self.clue.name}"
