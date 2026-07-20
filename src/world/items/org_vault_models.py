"""The org vault (#2540 Layer 4): logical custody of items held by an organization.

Ratified shape ("model B with model D's access surface"): custody, policy, and audit
live HERE — `OrganizationVault` mirrors `currency.OrganizationTreasury` (one per org,
get-or-create, a rank-gated authority knob) and `VaultHolding` rows carry the items.
A vaulted item's `holder_character_sheet` is null and its `game_object` is
dematerialized (row-only, the established pattern) — custody never depends on a
destructible physical object. The *where* (a bank room or a bank-access room feature)
is an action-layer prerequisite gate, deliberately not part of this layer; the
physical room-feature VAULT (#2179, `room_features.VaultDetails`) is a different
thing — a secure store for loose items in a room, not org custody.

`OrgVaultEvent` is the append-only audit rail (the `CurrencyTransfer` analogue for
items) — how embezzlement gets *discovered* later.
"""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.items.constants import OrgVaultEventKind, VaultTransitResolution


class OrganizationVault(SharedMemoryModel):
    """One per org (get-or-create): the item-custody twin of ``OrganizationTreasury``."""

    organization = models.OneToOneField(
        "societies.Organization",
        on_delete=models.CASCADE,
        related_name="item_vault",
    )
    withdraw_rank_max = models.PositiveSmallIntegerField(
        default=1,
        help_text=(
            "Members with rank tier <= this may withdraw (the spend_rank_max twin). "
            "Any active member may deposit."
        ),
    )

    class Meta:
        app_label = "items"

    def __str__(self) -> str:
        return f"Vault of {self.organization}"


class VaultHolding(SharedMemoryModel):
    """An item in an org's custody. Created on deposit, deleted on withdrawal."""

    vault = models.ForeignKey(
        OrganizationVault,
        on_delete=models.CASCADE,
        related_name="holdings",
    )
    item_instance = models.OneToOneField(
        "items.ItemInstance",
        on_delete=models.CASCADE,
        related_name="vault_holding",
    )
    deposited_by = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vault_deposits",
        help_text="Who put it in (audit; the withdrawal side lives on OrgVaultEvent).",
    )
    deposited_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "items"
        ordering = ["deposited_at"]

    def __str__(self) -> str:
        return f"item {self.item_instance_id} in {self.vault}"


class VaultTransit(SharedMemoryModel):
    """An item collected on the org's behalf, in a carrier's hands, owed to the vault.

    The gems return leg (#2540 ruling 2026-07-20): collection delivers everything into
    the collector's hands and mints one of these per item; depositing at the vault
    resolves it DEPOSITED (converting to a ``VaultHolding``), while the consent-gated
    embezzlement branch resolves it KEPT — the stone stays with the carrier and NO
    vault event is booked (the crime doesn't write itself into the org's ledger; the
    resolved transit row is the staff-side record, and the gap between the collection
    tally and the deposits is the in-world discovery hook). In-transit loss effects
    were considered and deliberately NOT built — loss lives in the collection roll.
    """

    vault = models.ForeignKey(
        OrganizationVault,
        on_delete=models.CASCADE,
        related_name="transits",
    )
    item_instance = models.OneToOneField(
        "items.ItemInstance",
        on_delete=models.CASCADE,
        related_name="vault_transit",
    )
    carrier_character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="vault_transits",
        help_text="The collector currently holding the item (sheet-scoped, like holders).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution = models.CharField(
        max_length=20,
        choices=VaultTransitResolution.choices,
        blank=True,
        default="",
        help_text="Blank while in transit; DEPOSITED or KEPT once resolved.",
    )

    class Meta:
        app_label = "items"
        ordering = ["created_at"]

    def __str__(self) -> str:
        state = self.resolution or "open"
        return f"transit item {self.item_instance_id} for {self.vault} ({state})"


class OrgVaultEvent(SharedMemoryModel):
    """Append-only vault audit row — the ``CurrencyTransfer`` analogue for items."""

    vault = models.ForeignKey(
        OrganizationVault,
        on_delete=models.CASCADE,
        related_name="events",
    )
    item_instance = models.ForeignKey(
        "items.ItemInstance",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="org_vault_events",
    )
    kind = models.CharField(max_length=20, choices=OrgVaultEventKind.choices)
    actor_persona = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="org_vault_events",
    )
    reason = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Short provenance note, e.g. 'boon' or 'tax collection deposit'.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "items"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.kind} item {self.item_instance_id} @ {self.vault}"
