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

from core.descriptors import ReverseOneToOneOrNone
from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.currency.constants import (
    GRAFT_DEFAULT_PCT,
    GRAFT_FLOOR_PCT,
    GRAFT_MAX_PCT,
    ContractFormality,
    ContractStatus,
    Denomination,
    IncomeStreamKind,
)

# Lazy model references (Django app_label.ModelName), extracted to satisfy S1192.
PERSONA_MODEL = "scenes.Persona"
ORGANIZATION_MODEL = "societies.Organization"


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
        ORGANIZATION_MODEL,
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


class FavorTokenDetails(SharedMemoryModel):
    """Per-instance details for a Golden Hare, an org-issued favor token (#2428).

    A gold coin bearing a rabbit with emerald eyes: one Hare = one deed done
    for ``issuing_organization``. Deliberately NOT coppers-denominated — a
    distinct instrument from ``CurrencyInstrumentDetails``, tradeable as an
    ordinary item via existing give/trade surfaces (no market machinery).
    Deed-provenance is story-significant: a redeemed row is never deleted,
    only stamped (``redeemed_at``), mirroring the items app's soft-delete
    norm for provenance-bearing instances.
    """

    item_instance = models.OneToOneField(
        "items.ItemInstance",
        on_delete=models.CASCADE,
        related_name="favor_token",
        help_text="The physical Golden Hare coin in the world.",
    )
    issuing_organization = models.ForeignKey(
        ORGANIZATION_MODEL,
        on_delete=models.PROTECT,
        related_name="issued_favor_tokens",
        help_text="The org this Hare represents a deed done for.",
    )
    provenance_note = models.CharField(
        max_length=200,
        help_text="The deed that minted this Hare.",
    )
    minted_at = models.DateTimeField(auto_now_add=True)
    redeemed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set when the Hare is surrendered/redeemed. Null = still owed.",
    )

    class Meta:
        verbose_name = "Favor Token"
        verbose_name_plural = "Favor Tokens"

    def __str__(self) -> str:
        state = "redeemed" if self.redeemed_at else "outstanding"
        return f"Golden Hare ({self.issuing_organization_id}, {state})"


class OrgEconomicsProfile(SharedMemoryModel):
    """Per-org economic state (#926): the Graft stat.

    Graft is a never-zero leak on income flows, driven by NPC servant
    dissatisfaction. Treating servants (a money sink) buys it down toward —
    but never to — the floor; investigating where the leak goes is mission
    content. Distinct from magic's Corruption by design.
    """

    organization = models.OneToOneField(
        ORGANIZATION_MODEL,
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
    """A recurring org income source (#926; active collection #930).

    Domain taxes and crime-turf kick-ups are the same machinery with
    different fictions. Income never lands passively: each cycle the gross
    accrues into ``uncollected_pool`` (no cap — ADR-0081), and money only
    reaches the treasury through an active collection dispatch whose graded
    outcome decides how much of the pool arrives. Graft leaks off the
    collected aggregate; the gross/net pair is recorded for declared-vs-
    actual obligations at collection time.
    """

    # Reverse-OneToOne safe accessor (#2386): missing row -> None.
    domain_holding_or_none = ReverseOneToOneOrNone("domain_holding")

    organization = models.ForeignKey(
        ORGANIZATION_MODEL,
        on_delete=models.CASCADE,
        related_name="income_streams",
    )
    name = models.CharField(max_length=100, help_text="e.g. 'Westrock land taxes'.")
    kind = models.CharField(max_length=20, choices=IncomeStreamKind.choices)
    gross_amount = models.PositiveBigIntegerField(help_text="Coppers per cycle before graft leaks.")
    uncollected_pool = models.PositiveBigIntegerField(
        default=0,
        help_text=(
            "Coppers amassed awaiting an active collection dispatch (#930). No cap: "
            "a hoarded pool is concentrated outcome risk, never a passive deposit."
        ),
    )
    area = models.ForeignKey(
        "areas.Area",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="income_streams",
        help_text=(
            "Where this stream's domain sits — feeds the collection-difficulty "
            "modifier from local order/crime when set (#930)."
        ),
    )
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
        ORGANIZATION_MODEL,
        on_delete=models.CASCADE,
        related_name="obligations_owed",
    )
    to_organization = models.ForeignKey(
        ORGANIZATION_MODEL,
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
        PERSONA_MODEL,
        on_delete=models.CASCADE,
        related_name="org_contributions",
    )
    organization = models.ForeignKey(
        ORGANIZATION_MODEL,
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

    Interest accrues monthly into ``arrears`` (basis points; 50 = the
    0.5%/mo reference). Servicing is **withholding at the income source**:
    every income payout pays down arrears before money reaches the books —
    honest debtors never manage debt, they just see smaller incomes, and
    over-leverage bottoms out at zero spendable income, never offscreen
    loss. The only road to consequences is the cheat: ``diverting`` routes
    income past the withholding (full money arrives, arrears balloon,
    exposure accrues). Getting caught is story content — staff/story sets
    ``in_default``; nothing mechanical ever flips it on its own.
    """

    debtor_organization = models.ForeignKey(
        ORGANIZATION_MODEL,
        on_delete=models.CASCADE,
        related_name="debts",
    )
    creditor_organization = models.ForeignKey(
        ORGANIZATION_MODEL,
        on_delete=models.CASCADE,
        related_name="loans_extended",
        help_text="The creditor (e.g. Blighton, the canonical NPC moneylender house).",
    )
    principal = models.PositiveBigIntegerField(help_text="Coppers owed.")
    interest_bps_monthly = models.PositiveSmallIntegerField(
        default=50,
        help_text="Monthly interest in basis points (50 = 0.5%/month).",
    )
    arrears = models.PositiveBigIntegerField(
        default=0,
        help_text="Accrued unpaid interest, withheld from incomes at source.",
    )
    diverting = models.BooleanField(
        default=False,
        help_text=(
            "The cheat: route income past the withholding. An active IC "
            "decision with discovery consequences — never a bookkeeping state."
        ),
    )
    in_default = models.BooleanField(
        default=False,
        help_text="Set by story/staff when a divert is CAUGHT — never automatic.",
    )
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


class Contract(SharedMemoryModel):
    """A consent-gated agreement between two economic parties (#928).

    Signing is THE consent moment — terms, stakes, and default consequences
    are all fixed before the counterparty accepts (mirrors the combat
    risk-acknowledgement pattern). Formality decides enforcement: NOTARIZED
    contracts settle automatically and can default; HANDSHAKE contracts are
    RP-only and the system never touches them after signing. Golden-rule
    scoping: the system enforces agreed terms; it never initiates
    antagonism.

    Each side is exactly one of (persona, organization) — typed nullable
    FK pairs like CurrencyTransfer.
    """

    proposer_persona = models.ForeignKey(
        PERSONA_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="contracts_proposed",
    )
    proposer_organization = models.ForeignKey(
        ORGANIZATION_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="contracts_proposed",
    )
    counterparty_persona = models.ForeignKey(
        PERSONA_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="contracts_received",
    )
    counterparty_organization = models.ForeignKey(
        ORGANIZATION_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="contracts_received",
    )
    title = models.CharField(max_length=120)
    terms = models.TextField(help_text="The agreed terms, exactly as shown at the consent moment.")
    formality = models.CharField(
        max_length=20,
        choices=ContractFormality.choices,
        default=ContractFormality.HANDSHAKE,
    )
    status = models.CharField(
        max_length=20,
        choices=ContractStatus.choices,
        default=ContractStatus.PROPOSED,
    )
    notary_organization = models.ForeignKey(
        ORGANIZATION_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contracts_notarized",
        help_text="The org that notarized (required for NOTARIZED formality).",
    )
    # Default-consequence menu, agreed at signing (#928). All optional.
    collateral_description = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Named collateral that cedes on default (story content).",
    )
    reputation_stake = models.BooleanField(
        default=False,
        help_text="Default carries reputation/standing damage.",
    )
    garnish_stream = models.ForeignKey(
        OrgIncomeStream,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="garnishing_contracts",
        help_text="Income stream liened at signing; garnished after default.",
    )
    garnish_percent = models.PositiveSmallIntegerField(
        default=0,
        validators=[MaxValueValidator(100)],
        help_text="Percent of the liened stream's net diverted after default.",
    )
    signed_at = models.DateTimeField(null=True, blank=True)
    consecutive_missed = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(proposer_persona__isnull=False)
                    ^ models.Q(proposer_organization__isnull=False)
                ),
                name="contract_one_proposer",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(counterparty_persona__isnull=False)
                    ^ models.Q(counterparty_organization__isnull=False)
                ),
                name="contract_one_counterparty",
            ),
        ]

    def __str__(self) -> str:
        return f"Contract({self.title}: {self.status})"

    @property
    def is_enforced(self) -> bool:
        return self.formality == ContractFormality.NOTARIZED


class ContractTerm(SharedMemoryModel):
    """One scheduled payment inside a contract (#928).

    ``payer_is_proposer`` picks the direction; recurring terms run every
    settlement cycle (stipends, pensions, patronage), one-shots run once
    (ransom payment, hired muscle's fee).
    """

    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name="payment_terms",
    )
    payer_is_proposer = models.BooleanField(
        help_text="True: proposer pays counterparty; False: the reverse.",
    )
    amount = models.PositiveBigIntegerField(help_text="Coppers per cycle.")
    recurring = models.BooleanField(
        default=False,
        help_text="Runs every settlement cycle until the contract ends.",
    )
    fulfilled = models.BooleanField(
        default=False,
        help_text="One-shot terms flip this after paying.",
    )

    class Meta:
        ordering = ["contract_id", "id"]

    def __str__(self) -> str:
        direction = "proposer→counterparty" if self.payer_is_proposer else "counterparty→proposer"
        return f"Term({self.amount}c {direction}{' recurring' if self.recurring else ''})"


class Profession(NaturalKeyMixin, SharedMemoryModel):
    """An on-grid job (#929): a wage rate bought with a locked AP allotment.

    The deliberate texture: a profession reserves the AP you'd otherwise
    adventure with — wealth buys back your week. Lower-class reference is
    1 silver (10c) per AP at 40 AP/week ≈ 4g/week; high-end ~10g/week.
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, default="")
    wage_per_ap = models.PositiveIntegerField(
        help_text="Coppers earned per reserved AP (10 = the lower-class 1s/AP)."
    )
    ap_reservation_weekly = models.PositiveSmallIntegerField(
        default=40,
        help_text="AP locked out of the pool each week to hold this job.",
    )
    chore_check_type = models.ForeignKey(
        "checks.CheckType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="professions",
        help_text="Check rolled for active on-grid chore work (up to 2× wages).",
    )

    objects = NaturalKeyManager()

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class CharacterEmployment(SharedMemoryModel):
    """A character's current job (#929). One active employment at a time."""

    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="employments",
    )
    profession = models.ForeignKey(
        Profession,
        on_delete=models.PROTECT,
        related_name="employees",
    )
    active = models.BooleanField(default=True)
    started_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-started_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["character_sheet"],
                condition=models.Q(active=True),
                name="one_active_employment_per_sheet",
            ),
        ]

    def __str__(self) -> str:
        return f"Employment({self.character_sheet_id}: {self.profession.name})"


class Business(SharedMemoryModel):
    """A persona-owned managed income venture (#929).

    Modest by design, with NEGATIVE variance — a bad week loses money.
    Investment raises the level; the top tiers (merchant princesses,
    hundreds of gold a week) live under constant story threat rather than
    mechanical safety.
    """

    owner_persona = models.ForeignKey(
        PERSONA_MODEL,
        on_delete=models.CASCADE,
        related_name="businesses",
    )
    name = models.CharField(max_length=120)
    invested = models.PositiveBigIntegerField(
        default=0,
        help_text="Total coppers sunk into the venture.",
    )
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "Businesses"
        constraints = [
            models.UniqueConstraint(
                fields=["owner_persona", "name"], name="business_name_unique_per_owner"
            ),
        ]

    def __str__(self) -> str:
        return f"Business({self.name}, L{self.level})"

    @property
    def level(self) -> int:
        from world.currency.constants import BUSINESS_INVESTMENT_PER_LEVEL  # noqa: PLC0415

        return 1 + self.invested // BUSINESS_INVESTMENT_PER_LEVEL


class DistinctionPurseDrain(SharedMemoryModel):
    """Config: a distinction that empties its holder's purse every week (#2613).

    The sidecar pattern for a non-modifier ongoing distinction effect, matching
    ``DistinctionAssetGrant`` (assets), ``DistinctionCodexGrant`` (codex), and
    ``DistinctionResonanceGrant`` (magic). Lives here, not in ``distinctions``,
    per ADR-0010: the consumer holds the FK pointing at the primitive, so
    ``distinctions`` stays dependency-free.

    Parameterized rather than a hardcoded slug lookup because siblings are
    certain — a Spendthrift at 50%, a tithe-bound character at 10%. Each is a
    data row, not new code.
    """

    distinction = models.OneToOneField(
        "distinctions.Distinction",
        on_delete=models.CASCADE,
        related_name="purse_drain",
        help_text="The distinction whose holders drain weekly.",
    )
    drain_percent = models.PositiveSmallIntegerField(
        default=100,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Percent of the drainable amount actually taken (100 = all of it).",
    )
    floor_coppers = models.PositiveBigIntegerField(
        default=0,
        help_text="Never drain the purse below this many coppers.",
    )

    class Meta:
        verbose_name = "Distinction Purse Drain"
        verbose_name_plural = "Distinction Purse Drains"

    def __str__(self) -> str:
        return f"PurseDrain({self.distinction_id}: {self.drain_percent}%)"


class PurseDrainWeek(SharedMemoryModel):
    """One holder's drain week: the opening baseline, and what came of it (#2613).

    The baseline is recorded in the ``SNAPSHOT`` cron band — *before* income
    lands — and consumed in the ``DRAIN`` band after obligations have paid.
    Those are separate tasks, so the value has to persist between them; it
    cannot be a local variable.

    Doubles as the audit trail. Without it the player-facing message can say
    that money vanished but not why that particular number did.
    """

    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="purse_drain_weeks",
    )
    game_week = models.ForeignKey(
        "game_clock.GameWeek",
        on_delete=models.CASCADE,
        related_name="purse_drain_weeks",
    )
    opening_balance = models.PositiveBigIntegerField(
        help_text="Purse balance at week start, before any income landed.",
    )
    snapshot_at = models.DateTimeField(
        help_text="When the baseline was taken — opens the outflow window.",
    )
    outflows = models.PositiveBigIntegerField(
        default=0,
        help_text=(
            "Total coppers that left the purse since snapshot_at — upkeep, dues, "
            "and ordinary spending alike. Any outgoing cost counts."
        ),
    )
    amount_drained = models.PositiveBigIntegerField(
        default=0,
        help_text="What the drain actually took.",
    )
    drained_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Null means the baseline exists but the drain has not run yet.",
    )

    class Meta:
        ordering = ["-game_week"]
        verbose_name = "Purse Drain Week"
        verbose_name_plural = "Purse Drain Weeks"
        constraints = [
            models.UniqueConstraint(
                fields=["character_sheet", "game_week"],
                name="purse_drain_week_unique_per_sheet",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"PurseDrainWeek({self.character_sheet_id}@{self.game_week_id}: "
            f"{self.opening_balance}c)"
        )
