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

from world.items.constants import OrgVaultEventKind


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
