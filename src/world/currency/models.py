"""Currency core models (#925 — economy umbrella #923).

Two ledgers (personal purse, org treasury), one audit trail, and the
physical instrument details row. Balances are integer coppers, always.

Holder convention follows the items precedent (#684): the purse anchors to
the **body** (CharacterSheet); persona presentation happens at serialization
time. Org treasuries anchor to ``societies.Organization`` with rank-gated
spend authority.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.currency.constants import Denomination


class CharacterPurse(SharedMemoryModel):
    """A character's personal money, in coppers."""

    character_sheet = models.OneToOneField(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="purse",
        help_text="Body-anchored holder (persona presentation at serialization).",
    )
    balance = models.PositiveBigIntegerField(
        default=0,
        help_text="Coppers on hand.",
    )

    def __str__(self) -> str:
        return f"Purse({self.character_sheet_id}: {self.balance}c)"


class OrganizationTreasury(SharedMemoryModel):
    """An organization's money, in coppers, with rank-gated spend authority."""

    organization = models.OneToOneField(
        "societies.Organization",
        on_delete=models.CASCADE,
        related_name="treasury",
        help_text="The org this treasury belongs to (house, family, guild).",
    )
    balance = models.PositiveBigIntegerField(
        default=0,
        help_text="Coppers in the treasury.",
    )
    spend_rank_max = models.PositiveSmallIntegerField(
        default=1,
        help_text=(
            "Highest rank NUMBER allowed to spend (rank 1 is the org's top; "
            "default 1 = leaders only). Members with rank <= this may spend."
        ),
    )

    def __str__(self) -> str:
        return f"Treasury({self.organization_id}: {self.balance}c)"


class CurrencyTransfer(SharedMemoryModel):
    """Audit row for every movement of money (#923: exact numbers in the ledger).

    Source/destination are typed nullable FKs: a null source is a **mint**
    (money entering the world — faucets), a null destination is a **sink**
    (money leaving it). Never both null.
    """

    from_purse = models.ForeignKey(
        CharacterPurse,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transfers_out",
    )
    from_treasury = models.ForeignKey(
        OrganizationTreasury,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transfers_out",
    )
    to_purse = models.ForeignKey(
        CharacterPurse,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transfers_in",
    )
    to_treasury = models.ForeignKey(
        OrganizationTreasury,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transfers_in",
    )
    amount = models.PositiveBigIntegerField(help_text="Coppers moved.")
    reason = models.CharField(
        max_length=200,
        help_text="Audit label (e.g. 'mission reward', 'tithe', 'mint fee').",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(from_purse__isnull=True) | models.Q(from_treasury__isnull=True)
                ),
                name="currency_transfer_single_source",
            ),
            models.CheckConstraint(
                condition=(models.Q(to_purse__isnull=True) | models.Q(to_treasury__isnull=True)),
                name="currency_transfer_single_destination",
            ),
            models.CheckConstraint(
                condition=~(
                    models.Q(from_purse__isnull=True)
                    & models.Q(from_treasury__isnull=True)
                    & models.Q(to_purse__isnull=True)
                    & models.Q(to_treasury__isnull=True)
                ),
                name="currency_transfer_not_void",
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="currency_transfer_positive_amount",
            ),
        ]

    def __str__(self) -> str:
        return f"Transfer({self.amount}c: {self.reason})"

    def clean(self) -> None:
        super().clean()
        if self.from_purse_id and self.from_treasury_id:
            msg = "A transfer has at most one source."
            raise ValidationError(msg)
        if self.to_purse_id and self.to_treasury_id:
            msg = "A transfer has at most one destination."
            raise ValidationError(msg)


class CurrencyInstrumentDetails(SharedMemoryModel):
    """Per-kind details for a minted physical coin (items precedent).

    Ledgers never read "3 Countesses" — instruments exist for theater,
    transport, and theft. Face value is denormalized at mint time so the
    coin survives any later ladder retuning.
    """

    item_instance = models.OneToOneField(
        "items.ItemInstance",
        on_delete=models.CASCADE,
        related_name="currency_instrument",
        help_text="The physical coin in the world.",
    )
    denomination = models.CharField(
        max_length=20,
        choices=Denomination.choices,
    )
    face_value = models.PositiveBigIntegerField(
        help_text="Coppers this instrument redeems for (denormalized at mint).",
    )

    class Meta:
        verbose_name = "Currency Instrument"
        verbose_name_plural = "Currency Instruments"

    def __str__(self) -> str:
        return f"{self.get_denomination_display()} ({self.face_value}c)"
