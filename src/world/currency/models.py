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
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.currency.constants import (
    GRAFT_DEFAULT_PCT,
    GRAFT_FLOOR_PCT,
    GRAFT_MAX_PCT,
    Denomination,
    IncomeStreamKind,
)


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


class OrgEconomicsProfile(SharedMemoryModel):
    """Per-org economic state (#926): the Graft stat.

    Graft is a never-zero leak on income flows, driven by NPC servant
    dissatisfaction. Treating servants (a money sink) buys it down toward —
    but never to — the floor; investigating where the leak goes is mission
    content. Distinct from magic's Corruption by design.
    """

    organization = models.OneToOneField(
        "societies.Organization",
        on_delete=models.CASCADE,
        related_name="economics",
        help_text="The org this economic profile belongs to.",
    )
    graft_pct = models.PositiveSmallIntegerField(
        default=GRAFT_DEFAULT_PCT,
        validators=[MinValueValidator(GRAFT_FLOOR_PCT), MaxValueValidator(GRAFT_MAX_PCT)],
        help_text=(
            "Percent of every income flow lost to graft. Floored above zero "
            "by doctrine — some leak always survives."
        ),
    )

    class Meta:
        verbose_name = "Org Economics Profile"
        verbose_name_plural = "Org Economics Profiles"

    def __str__(self) -> str:
        return f"Economics({self.organization_id}: graft {self.graft_pct}%)"


class OrgIncomeStream(SharedMemoryModel):
    """A recurring org income source (#926).

    Domain taxes and crime-turf kick-ups are the same machinery with
    different fictions: a gross amount flows in per cycle, graft leaks off
    the top, the net lands in the treasury, and the gross/net pair is
    recorded for declared-vs-actual obligations.
    """

    organization = models.ForeignKey(
        "societies.Organization",
        on_delete=models.CASCADE,
        related_name="income_streams",
    )
    name = models.CharField(max_length=100, help_text="e.g. 'Westrock land taxes'.")
    kind = models.CharField(max_length=20, choices=IncomeStreamKind.choices)
    gross_amount = models.PositiveBigIntegerField(help_text="Coppers per cycle before graft leaks.")
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["organization_id", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"], name="org_income_stream_name_unique"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_kind_display()}: {self.gross_amount}c)"


class IncomeDeclaration(SharedMemoryModel):
    """Declared-vs-actual record for one income payout (#926).

    Percentage obligations (tithes, taxes, dues) compute on the DECLARED
    amount. Under-declaring is a player action with discovery consequences —
    this row is the evidence trail: actual and declared live side by side so
    a discovery check has something to discover.
    """

    stream = models.ForeignKey(
        OrgIncomeStream,
        on_delete=models.CASCADE,
        related_name="declarations",
    )
    actual_amount = models.PositiveBigIntegerField(
        help_text="Net coppers actually received (after graft)."
    )
    declared_amount = models.PositiveBigIntegerField(
        help_text="Coppers declared for obligation computation."
    )
    settled = models.BooleanField(
        default=False,
        help_text="Obligations have been computed against this declaration.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Declaration({self.stream_id}: {self.declared_amount}/{self.actual_amount}c)"

    @property
    def underdeclared(self) -> bool:
        return self.declared_amount < self.actual_amount


class OrgObligation(SharedMemoryModel):
    """A standing percent-of-declared-income obligation between orgs (#926).

    One mechanic covers tithes (to the Faith), taxes (to the liege), and
    dues (to a guild): ``percent`` of the payer's declared income moves
    treasury→treasury at settlement.
    """

    from_organization = models.ForeignKey(
        "societies.Organization",
        on_delete=models.CASCADE,
        related_name="obligations_owed",
    )
    to_organization = models.ForeignKey(
        "societies.Organization",
        on_delete=models.CASCADE,
        related_name="obligations_due",
    )
    name = models.CharField(max_length=100, help_text="e.g. 'Crown taxes', 'Faith tithe'.")
    percent = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Percent of declared income owed per settlement.",
    )
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["from_organization_id", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["from_organization", "to_organization", "name"],
                name="org_obligation_unique",
            ),
            models.CheckConstraint(
                condition=~models.Q(from_organization=models.F("to_organization")),
                name="org_obligation_not_self",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.name}: {self.percent}% ({self.from_organization_id}→{self.to_organization_id})"
        )


class ContributionRecord(SharedMemoryModel):
    """A member's contribution to their org's treasury (#926).

    Consumed by tithes and the management screen (family books, #930):
    who put what in, when, and why.
    """

    persona = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.CASCADE,
        related_name="org_contributions",
    )
    organization = models.ForeignKey(
        "societies.Organization",
        on_delete=models.CASCADE,
        related_name="contributions",
    )
    amount = models.PositiveBigIntegerField(help_text="Coppers contributed.")
    reason = models.CharField(max_length=200, blank=True, default="")
    transfer = models.ForeignKey(
        CurrencyTransfer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contribution_records",
        help_text="The ledger row this contribution rode on.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Contribution({self.persona_id}→{self.organization_id}: {self.amount}c)"


class DebtInstrument(SharedMemoryModel):
    """A standing debt on an org treasury (#927).

    Interest accrues monthly (basis points; 50 = the 0.5%/mo reference).
    The stasis principle governs servicing: in absentia the books run
    themselves (auto_service pays interest first, before upkeep/wages), and
    **default can only fire on an active decision to divert** — turning
    auto_service off is that decision. A funds-short month under
    auto-service records a miss but never defaults anyone offscreen.
    Two consecutive misses while diverting = default (named-asset cession
    and political exposure are story content keyed off ``in_default``).
    """

    debtor_organization = models.ForeignKey(
        "societies.Organization",
        on_delete=models.CASCADE,
        related_name="debts",
    )
    creditor_organization = models.ForeignKey(
        "societies.Organization",
        on_delete=models.CASCADE,
        related_name="loans_extended",
        help_text="The creditor (e.g. Blighton, the canonical NPC moneylender house).",
    )
    principal = models.PositiveBigIntegerField(help_text="Coppers owed.")
    interest_bps_monthly = models.PositiveSmallIntegerField(
        default=50,
        help_text="Monthly interest in basis points (50 = 0.5%/month).",
    )
    auto_service = models.BooleanField(
        default=True,
        help_text=(
            "Books run themselves: pay interest automatically, first in "
            "priority. Turning this off is the active divert decision that "
            "makes default possible."
        ),
    )
    consecutive_missed = models.PositiveSmallIntegerField(default=0)
    in_default = models.BooleanField(default=False)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(debtor_organization=models.F("creditor_organization")),
                name="debt_not_self",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"Debt({self.debtor_organization_id}→{self.creditor_organization_id}: "
            f"{self.principal}c @ {self.interest_bps_monthly}bps)"
        )

    @property
    def monthly_interest(self) -> int:
        return self.principal * self.interest_bps_monthly // 10000
