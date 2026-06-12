"""Currency services (#925): the one path money moves through.

``transfer`` is the single mutation point — every faucet, sink, payment,
tithe, and fee in the economy routes here (mission rewards replace their
money stub with a mint-shaped call; permits/teaching fees route their costs
as sinks or transfers). Atomic, row-locked, audited.
"""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from world.currency.constants import (
    ACTIVE_WEEK_LOGIN_DAYS,
    BUSINESS_BASE_WEEKLY_PER_LEVEL,
    BUSINESS_FORTUNE_MAX,
    BUSINESS_FORTUNE_MIN,
    CHORE_MULTIPLIER_CRIT,
    CHORE_MULTIPLIER_FAIL,
    CHORE_MULTIPLIER_SUCCESS,
    CONTRACT_DEFAULT_AFTER_MISSES,
    DENOMINATION_VALUES,
    GRAFT_FLOOR_PCT,
    MINT_FEE_PCT,
    NOTARY_FEE_COPPERS,
    ContractFormality,
    ContractStatus,
    format_coppers,
)
from world.currency.models import (
    Business,
    CharacterEmployment,
    CharacterPurse,
    Contract,
    ContractTerm,
    ContributionRecord,
    CurrencyInstrumentDetails,
    CurrencyTransfer,
    DebtInstrument,
    IncomeDeclaration,
    OrganizationTreasury,
    OrgEconomicsProfile,
    OrgIncomeStream,
    OrgObligation,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.items.models import ItemInstance
    from world.scenes.models import Persona
    from world.societies.models import Organization


def get_or_create_purse(character_sheet: CharacterSheet) -> CharacterPurse:
    purse, _ = CharacterPurse.objects.get_or_create(character_sheet=character_sheet)
    return purse


def get_or_create_treasury(organization: Organization) -> OrganizationTreasury:
    treasury, _ = OrganizationTreasury.objects.get_or_create(organization=organization)
    return treasury


def can_spend_treasury(treasury: OrganizationTreasury, persona: Persona) -> bool:
    """Spend authority: an active membership at rank <= spend_rank_max."""
    from world.societies.models import OrganizationMembership  # noqa: PLC0415

    return OrganizationMembership.objects.filter(
        persona=persona,
        organization_id=treasury.organization_id,
        rank__lte=treasury.spend_rank_max,
    ).exists()


def transfer(  # noqa: PLR0913 - source/destination pairs are co-equal by design
    *,
    amount: int,
    reason: str,
    from_purse: CharacterPurse | None = None,
    from_treasury: OrganizationTreasury | None = None,
    to_purse: CharacterPurse | None = None,
    to_treasury: OrganizationTreasury | None = None,
) -> CurrencyTransfer:
    """Move ``amount`` coppers; null source = mint (faucet), null dest = sink.

    Atomic with row locks; raises ValidationError on a non-positive amount,
    a void transfer (no source AND no destination), double sources or
    destinations, or insufficient funds.
    """
    if amount <= 0:
        msg = "Transfers move a positive number of coppers."
        raise ValidationError(msg)
    if from_purse is not None and from_treasury is not None:
        msg = "A transfer has at most one source."
        raise ValidationError(msg)
    if to_purse is not None and to_treasury is not None:
        msg = "A transfer has at most one destination."
        raise ValidationError(msg)
    source = from_purse or from_treasury
    destination = to_purse or to_treasury
    if source is None and destination is None:
        msg = "A transfer needs a source or a destination."
        raise ValidationError(msg)

    with transaction.atomic():
        if source is not None:
            source = type(source).objects.select_for_update().get(pk=source.pk)
            if source.balance < amount:
                msg = f"Insufficient funds: {format_coppers(source.balance)} on hand."
                raise ValidationError(msg)
            source.balance -= amount
            source.save(update_fields=["balance"])
        if destination is not None:
            destination = type(destination).objects.select_for_update().get(pk=destination.pk)
            destination.balance += amount
            destination.save(update_fields=["balance"])
        return CurrencyTransfer.objects.create(
            from_purse=from_purse,
            from_treasury=from_treasury,
            to_purse=to_purse,
            to_treasury=to_treasury,
            amount=amount,
            reason=reason,
        )


def _instrument_template(denomination: str):
    """Lazy ItemTemplate per denomination (repo bans seed migrations).

    PLACEHOLDER descriptions — instrument flavor text is an authored-content
    pass for Apostate.
    """
    from world.currency.constants import Denomination  # noqa: PLC0415
    from world.items.models import ItemTemplate  # noqa: PLC0415

    label = Denomination(denomination).label
    template, _ = ItemTemplate.objects.get_or_create(
        name=f"{label} (coin)",
        defaults={
            "description": (
                f"PLACEHOLDER A minted {label}, worth "
                f"{format_coppers(DENOMINATION_VALUES[denomination])}."
            ),
        },
    )
    return template


def mint_instrument(
    *,
    denomination: str,
    holder_sheet: CharacterSheet,
    from_purse: CharacterPurse | None = None,
    from_treasury: OrganizationTreasury | None = None,
) -> ItemInstance:
    """Convert ledger money into a physical coin (face value + mint fee).

    The fee is a sink (#923); the face value is *conserved* — it leaves the
    ledger and lives inside the instrument until redemption.
    """
    from world.items.models import ItemInstance  # noqa: PLC0415

    face_value = DENOMINATION_VALUES[denomination]
    fee = int(face_value * MINT_FEE_PCT)
    with transaction.atomic():
        transfer(
            amount=face_value,
            reason=f"mint {denomination}",
            from_purse=from_purse,
            from_treasury=from_treasury,
        )
        if fee:
            transfer(
                amount=fee,
                reason=f"mint fee {denomination}",
                from_purse=from_purse,
                from_treasury=from_treasury,
            )
        instance = ItemInstance.objects.create(
            template=_instrument_template(denomination),
            holder_character_sheet=holder_sheet,
        )
        CurrencyInstrumentDetails.objects.create(
            item_instance=instance,
            denomination=denomination,
            face_value=face_value,
        )
    return instance


def redeem_instrument(
    *,
    instance: ItemInstance,
    to_purse: CharacterPurse | None = None,
    to_treasury: OrganizationTreasury | None = None,
) -> CurrencyTransfer:
    """Convert a physical coin back into ledger money (fee-free).

    Consumes the instrument (the coin is melted back into the books).
    """
    details = CurrencyInstrumentDetails.objects.get(item_instance=instance)
    with transaction.atomic():
        row = transfer(
            amount=details.face_value,
            reason=f"redeem {details.denomination}",
            to_purse=to_purse,
            to_treasury=to_treasury,
        )
        instance.delete()
    return row


def get_or_create_economics(organization: Organization) -> OrgEconomicsProfile:
    economics, _ = OrgEconomicsProfile.objects.get_or_create(organization=organization)
    return economics


@transaction.atomic
def process_income_stream(
    stream: OrgIncomeStream,
    *,
    declared_amount: int | None = None,
) -> IncomeDeclaration:
    """Pay out one income-stream cycle (#926).

    Graft leaks off the gross first (never reaches the treasury at all —
    where it goes is mission content, not a ledger row); the net mints into
    the org treasury via the audited transfer path; an IncomeDeclaration
    records actual-vs-declared for obligation settlement. ``declared_amount``
    defaults to the honest number — under-declaring is a deliberate caller
    action with discovery consequences.
    """
    if not stream.active:
        msg = "This income stream is inactive."
        raise ValidationError(msg)

    economics = get_or_create_economics(stream.organization)
    leak = stream.gross_amount * economics.graft_pct // 100
    net = stream.gross_amount - leak

    treasury = get_or_create_treasury(stream.organization)
    if net > 0:
        transfer(
            amount=net,
            reason=f"income: {stream.name}",
            to_treasury=treasury,
        )

    # Costs come off before the money is "yours" (#927): debt service
    # withholds at the source, then any defaulted-contract liens (#928).
    _withhold_debt_service(stream, treasury, net)
    _enforce_garnishments(stream, treasury, net)

    declared = net if declared_amount is None else declared_amount
    return IncomeDeclaration.objects.create(
        stream=stream,
        actual_amount=net,
        declared_amount=declared,
    )


@transaction.atomic
def settle_obligations(organization: Organization) -> list[CurrencyTransfer]:
    """Settle all active obligations against unsettled declared income (#926).

    One mechanic for tithes, taxes, and dues: each obligation takes its
    percent of the org's unsettled DECLARED total, treasury→treasury.
    Declarations are marked settled afterward, so each is obligated once.
    """
    declarations = list(
        IncomeDeclaration.objects.filter(
            stream__organization=organization,
            settled=False,
        )
    )
    declared_total = sum(d.declared_amount for d in declarations)
    if declared_total == 0:
        return []

    transfers: list[CurrencyTransfer] = []
    from_treasury = get_or_create_treasury(organization)
    for obligation in OrgObligation.objects.filter(from_organization=organization, active=True):
        amount = declared_total * obligation.percent // 100
        if amount == 0:
            continue
        transfers.append(
            transfer(
                amount=amount,
                reason=f"obligation: {obligation.name}",
                from_treasury=from_treasury,
                to_treasury=get_or_create_treasury(obligation.to_organization),
            )
        )

    IncomeDeclaration.objects.filter(pk__in=[d.pk for d in declarations]).update(settled=True)
    return transfers


@transaction.atomic
def record_contribution(
    *,
    persona: Persona,
    organization: Organization,
    amount: int,
    reason: str = "",
) -> ContributionRecord:
    """A member pays into the org treasury, on the books (#926).

    Moves purse→treasury through the audited path and writes the
    ContributionRecord the management screen and tithes consume.
    """
    purse = get_or_create_purse(persona.character_sheet)
    ledger_row = transfer(
        amount=amount,
        reason=f"contribution: {organization.name}",
        from_purse=purse,
        to_treasury=get_or_create_treasury(organization),
    )
    return ContributionRecord.objects.create(
        persona=persona,
        organization=organization,
        amount=amount,
        reason=reason,
        transfer=ledger_row,
    )


@transaction.atomic
def treat_servants(
    organization: Organization,
    *,
    payment: int,
    graft_reduction: int,
) -> OrgEconomicsProfile:
    """Spend treasury money treating servants to buy graft down (#926).

    A sink that buys efficiency: the payment leaves the world (null
    destination), and graft drops by ``graft_reduction`` — floored above
    zero by doctrine. Pricing curves are content; callers decide what a
    point costs.
    """
    if graft_reduction <= 0:
        msg = "Graft reduction must be positive."
        raise ValidationError(msg)

    treasury = get_or_create_treasury(organization)
    transfer(
        amount=payment,
        reason="treating servants",
        from_treasury=treasury,
    )
    economics = get_or_create_economics(organization)
    economics.graft_pct = max(GRAFT_FLOOR_PCT, economics.graft_pct - graft_reduction)
    economics.save(update_fields=["graft_pct"])
    return economics


@transaction.atomic
def extend_loan(
    *,
    creditor: Organization,
    debtor: Organization,
    principal: int,
    interest_bps_monthly: int = 50,
    fiat: bool = False,
) -> DebtInstrument:
    """Create a loan: principal moves creditor→debtor, instrument records it (#927).

    ``fiat`` mints the principal instead of drawing the creditor's treasury —
    for NPC moneylenders whose books exist only as fiction (Blighton's vaults
    are not a player-visible balance).
    """
    transfer(
        amount=principal,
        reason=f"loan principal: {creditor.name}",
        from_treasury=None if fiat else get_or_create_treasury(creditor),
        to_treasury=get_or_create_treasury(debtor),
    )
    return DebtInstrument.objects.create(
        debtor_organization=debtor,
        creditor_organization=creditor,
        principal=principal,
        interest_bps_monthly=interest_bps_monthly,
    )


def accrue_monthly_interest(organization: Organization) -> int:
    """One month's interest lands in arrears (#927). Returns total accrued.

    No money moves here — arrears are withheld from incomes at the source
    by ``process_income_stream``. Run by the monthly cron (#932).
    """
    total = 0
    for debt in DebtInstrument.objects.filter(debtor_organization=organization, active=True):
        interest = debt.monthly_interest
        if interest <= 0:
            continue
        debt.arrears += interest
        debt.save(update_fields=["arrears"])
        total += interest
    return total


def _withhold_debt_service(
    stream: OrgIncomeStream, treasury: OrganizationTreasury, available: int
) -> int:
    """Pay down arrears at the income source (#927). Returns coppers withheld.

    Oldest debt first; capped at the income available — over-leverage
    bottoms out at zero spendable income, never seizure. Diverting debts
    are skipped: that money reaches the books whole, the arrears keep
    growing, and discovery is the player-facing risk loop.
    """
    withheld = 0
    debts = DebtInstrument.objects.filter(
        debtor_organization=stream.organization,
        active=True,
        diverting=False,
        arrears__gt=0,
    ).order_by("created_at")
    for debt in debts:
        if available <= 0:
            break
        payment = min(debt.arrears, available)
        transfer(
            amount=payment,
            reason=f"debt service: {debt.creditor_organization.name}",
            from_treasury=treasury,
            to_treasury=get_or_create_treasury(debt.creditor_organization),
        )
        debt.arrears -= payment
        debt.save(update_fields=["arrears"])
        available -= payment
        withheld += payment
    return withheld


@transaction.atomic
def repay_principal(debt: DebtInstrument, amount: int) -> CurrencyTransfer:
    """Pay down (or off) a debt's principal, treasury→treasury (#927)."""
    if amount <= 0 or amount > debt.principal:
        msg = "Repayment must be positive and at most the outstanding principal."
        raise ValidationError(msg)
    row = transfer(
        amount=amount,
        reason=f"loan repayment: {debt.creditor_organization.name}",
        from_treasury=get_or_create_treasury(debt.debtor_organization),
        to_treasury=get_or_create_treasury(debt.creditor_organization),
    )
    debt.principal -= amount
    update_fields = ["principal"]
    if debt.principal == 0:
        debt.active = False
        update_fields.append("active")
    debt.save(update_fields=update_fields)
    return row


def _enforce_garnishments(
    stream: OrgIncomeStream, treasury: OrganizationTreasury, net: int
) -> None:
    """Divert liened income from a defaulted contract's stream (#928).

    The lien was agreed at signing; enforcement only begins after default —
    the system enforces agreed terms, it never initiates antagonism.
    """
    for lien in Contract.objects.filter(
        garnish_stream=stream,
        status=ContractStatus.DEFAULTED,
        garnish_percent__gt=0,
    ):
        amount = net * lien.garnish_percent // 100
        if amount == 0:
            continue
        defaulter_is_proposer = lien.proposer_organization_id == stream.organization_id
        to_purse, to_treasury = _party_accounts(lien, proposer=not defaulter_is_proposer)
        transfer(
            amount=amount,
            reason=f"garnishment: {lien.title}",
            from_treasury=treasury,
            to_purse=to_purse,
            to_treasury=to_treasury,
        )


def _party_accounts(
    contract: Contract, *, proposer: bool
) -> tuple[CharacterPurse | None, OrganizationTreasury | None]:
    """Resolve one contract side to its money container (purse XOR treasury)."""
    persona = contract.proposer_persona if proposer else contract.counterparty_persona
    organization = (
        contract.proposer_organization if proposer else contract.counterparty_organization
    )
    if persona is not None:
        return get_or_create_purse(persona.character_sheet), None
    if organization is None:  # pragma: no cover - DB constraint guards this
        msg = "Contract side has no party."
        raise ValidationError(msg)
    return None, get_or_create_treasury(organization)


@transaction.atomic
def sign_contract(contract: Contract) -> Contract:
    """The consent moment (#928): counterparty accepts the fixed terms.

    Terms, stakes, and the default-consequence menu must already be on the
    row — nothing about the deal may change after consent. Notarized
    contracts charge the notary fee (a sink) from the proposer's side and
    require a notary org. Handshakes activate with no machinery.
    """
    if contract.status != ContractStatus.PROPOSED:
        msg = "Only a proposed contract can be signed."
        raise ValidationError(msg)
    if contract.formality == ContractFormality.NOTARIZED:
        if contract.notary_organization is None:
            msg = "Notarized contracts need a notary organization."
            raise ValidationError(msg)
        purse, treasury = _party_accounts(contract, proposer=True)
        transfer(
            amount=NOTARY_FEE_COPPERS,
            reason=f"notary fee: {contract.title}",
            from_purse=purse,
            from_treasury=treasury,
        )
    contract.status = ContractStatus.ACTIVE
    contract.signed_at = timezone.now()
    contract.save(update_fields=["status", "signed_at"])
    return contract


def _pay_contract_term(contract: Contract, term: ContractTerm) -> CurrencyTransfer | None:
    """Pay one term payer→payee; None on insufficient funds (a miss)."""
    from_purse, from_treasury = _party_accounts(contract, proposer=term.payer_is_proposer)
    to_purse, to_treasury = _party_accounts(contract, proposer=not term.payer_is_proposer)
    try:
        return transfer(
            amount=term.amount,
            reason=f"contract: {contract.title}",
            from_purse=from_purse,
            from_treasury=from_treasury,
            to_purse=to_purse,
            to_treasury=to_treasury,
        )
    except ValidationError:
        return None


@transaction.atomic
def settle_contract_cycle(contract: Contract) -> list[CurrencyTransfer]:
    """Run one settlement cycle for an ACTIVE notarized contract (#928).

    Due terms (unfulfilled one-shots + all recurring) pay payer→payee. A
    funds-short cycle counts one miss; CONTRACT_DEFAULT_AFTER_MISSES
    consecutive misses flips the contract DEFAULTED — activating the agreed
    consequence menu (the garnishment lien is enforced by
    process_income_stream; collateral/reputation are story content). When
    no recurring terms remain and every one-shot is fulfilled, the
    contract COMPLETES. Handshake contracts are never settled — RP only.
    """
    if not contract.is_enforced:
        msg = "Handshake contracts are not enforced by the system."
        raise ValidationError(msg)
    if contract.status != ContractStatus.ACTIVE:
        msg = "Only active contracts settle."
        raise ValidationError(msg)

    transfers: list[CurrencyTransfer] = []
    missed = False
    terms = list(contract.payment_terms.all())
    for term in terms:
        if term.fulfilled and not term.recurring:
            continue
        row = _pay_contract_term(contract, term)
        if row is None:
            missed = True
            continue
        transfers.append(row)
        if not term.recurring:
            term.fulfilled = True
            term.save(update_fields=["fulfilled"])

    _update_contract_status(contract, terms=terms, missed=missed)
    return transfers


def _update_contract_status(contract: Contract, *, terms: list[ContractTerm], missed: bool) -> None:
    """Advance miss counters / default / completion after a settlement pass."""
    if missed:
        contract.consecutive_missed += 1
        update_fields = ["consecutive_missed"]
        if contract.consecutive_missed >= CONTRACT_DEFAULT_AFTER_MISSES:
            contract.status = ContractStatus.DEFAULTED
            update_fields.append("status")
        contract.save(update_fields=update_fields)
        return

    if contract.consecutive_missed:
        contract.consecutive_missed = 0
        contract.save(update_fields=["consecutive_missed"])

    has_recurring = any(t.recurring for t in terms)
    all_oneshots_done = all(t.fulfilled for t in terms if not t.recurring)
    if not has_recurring and all_oneshots_done:
        contract.status = ContractStatus.COMPLETED
        contract.save(update_fields=["status"])


@transaction.atomic
def run_weekly_employment(employment: CharacterEmployment, *, was_active: bool) -> int:
    """One week's automated wages for a held job (#929).

    The profession's AP allotment is locked first — spent from the pool
    exactly like adventuring AP would be, because it IS the AP you'd have
    adventured with. Wages mint on the AP actually reserved, and ONLY for
    a week the character was actively played (the activity signal comes
    from the weekly cron, #932). Returns coppers paid.
    """
    from world.action_points.models import ActionPointPool  # noqa: PLC0415

    if not employment.active or not was_active:
        return 0

    pool = ActionPointPool.get_or_create_for_character(employment.character_sheet.character)
    reserved = min(employment.profession.ap_reservation_weekly, pool.current)
    if reserved <= 0:
        return 0
    if not pool.spend(reserved):  # pragma: no cover - min() guards this
        return 0

    wages = reserved * employment.profession.wage_per_ap
    transfer(
        amount=wages,
        reason=f"wages: {employment.profession.name}",
        to_purse=get_or_create_purse(employment.character_sheet),
    )
    return wages


@transaction.atomic
def work_chore(employment: CharacterEmployment, *, ap_spent: int) -> int:
    """Active on-grid chore work (#929): spend AP now, roll, earn up to 2×.

    Rolls the profession's chore check through perform_check — character
    identity always matters. success_level maps to the wage multiplier
    (fail 1×, success 1.5×, strong success 2×). Returns coppers paid.
    """
    from world.action_points.models import ActionPointPool  # noqa: PLC0415
    from world.checks.services import perform_check  # noqa: PLC0415

    if not employment.active:
        msg = "You do not hold that job."
        raise ValidationError(msg)
    if ap_spent <= 0:
        msg = "Chore work needs AP."
        raise ValidationError(msg)

    pool = ActionPointPool.get_or_create_for_character(employment.character_sheet.character)
    if not pool.spend(ap_spent):
        msg = "Not enough AP."
        raise ValidationError(msg)

    multiplier = CHORE_MULTIPLIER_FAIL
    if employment.profession.chore_check_type is not None:
        result = perform_check(
            employment.character_sheet.character,
            employment.profession.chore_check_type,
        )
        if result.success_level >= 2:  # noqa: PLR2004 - chart success degrees
            multiplier = CHORE_MULTIPLIER_CRIT
        elif result.success_level >= 1:
            multiplier = CHORE_MULTIPLIER_SUCCESS

    wages = ap_spent * employment.profession.wage_per_ap * multiplier // 100
    if wages > 0:
        transfer(
            amount=wages,
            reason=f"chore wages: {employment.profession.name}",
            to_purse=get_or_create_purse(employment.character_sheet),
        )
    return wages


@transaction.atomic
def invest_in_business(business: Business, *, amount: int) -> Business:
    """Sink owner money into a venture (#929); investment raises the level."""
    if amount <= 0:
        msg = "Investment must be positive."
        raise ValidationError(msg)
    transfer(
        amount=amount,
        reason=f"investment: {business.name}",
        from_purse=get_or_create_purse(business.owner_persona.character_sheet),
    )
    business.invested += amount
    business.save(update_fields=["invested"])
    return business


@transaction.atomic
def run_business_week(business: Business, *, fortune: int) -> int:
    """One week's business result (#929). ``fortune`` is -100..100.

    The weekly cron supplies fortune (a roll, market events, story).
    Yield = level × base × (100 + fortune) / 100 − level × base, i.e.
    fortune IS the profit/loss percentage on the level's base turnover —
    a bad week (negative fortune) draws real money from the owner's purse.
    Returns signed coppers (negative = loss taken).
    """
    if not business.active:
        return 0
    fortune = max(-100, min(100, fortune))
    base = business.level * BUSINESS_BASE_WEEKLY_PER_LEVEL
    net = base * fortune // 100
    purse = get_or_create_purse(business.owner_persona.character_sheet)
    if net > 0:
        transfer(amount=net, reason=f"business profit: {business.name}", to_purse=purse)
    elif net < 0:
        loss = min(-net, purse.balance)  # can't lose money you don't have
        if loss > 0:
            transfer(amount=loss, reason=f"business loss: {business.name}", from_purse=purse)
        net = -loss
    return net


def run_weekly_economy() -> dict[str, int]:
    """The Sunday-rollover economy pass (#932). Returns per-phase counts.

    Order matters: interest accrues into arrears FIRST so this week's
    income withholding services this week's interest; then income streams
    flow (graft → debt withholding → garnishment → declaration); then
    notarized contracts settle; then employment wages pay for
    actively-played weeks; then businesses roll their fortune. Each phase
    isolates failures per row — one broken org never wedges the rollover.
    """
    return {
        "interest": _weekly_interest_accrual(),
        "income": _weekly_income_streams(),
        "contracts": _weekly_contract_settlement(),
        "wages": _weekly_wages(),
        "businesses": _weekly_business_fortunes(),
    }


def _weekly_interest_accrual() -> int:
    """Weekly fraction of the monthly reference rate lands in arrears."""
    count = 0
    for debt in DebtInstrument.objects.filter(active=True):
        try:
            weekly = debt.monthly_interest // 4
            if weekly > 0:
                debt.arrears += weekly
                debt.save(update_fields=["arrears"])
                count += 1
        except Exception:
            logger.exception("weekly economy: interest accrual failed for debt %s", debt.pk)
    return count


def _weekly_income_streams() -> int:
    count = 0
    for stream in OrgIncomeStream.objects.filter(active=True).select_related("organization"):
        try:
            process_income_stream(stream)
            count += 1
        except Exception:
            logger.exception("weekly economy: income stream %s failed", stream.pk)
    return count


def _weekly_contract_settlement() -> int:
    count = 0
    for contract in Contract.objects.filter(
        status=ContractStatus.ACTIVE, formality=ContractFormality.NOTARIZED
    ):
        try:
            settle_contract_cycle(contract)
            count += 1
        except Exception:
            logger.exception("weekly economy: contract %s settlement failed", contract.pk)
    return count


def _weekly_wages() -> int:
    from django.utils import timezone as dj_timezone  # noqa: PLC0415

    count = 0
    cutoff = dj_timezone.now() - timedelta(days=ACTIVE_WEEK_LOGIN_DAYS)
    for employment in CharacterEmployment.objects.filter(active=True).select_related(
        "character_sheet", "profession"
    ):
        try:
            account = employment.character_sheet.character.db_account
            was_active = bool(
                account is not None
                and account.last_login is not None
                and account.last_login >= cutoff
            )
            run_weekly_employment(employment, was_active=was_active)
            count += 1
        except Exception:
            logger.exception("weekly economy: wages failed for employment %s", employment.pk)
    return count


def _weekly_business_fortunes() -> int:
    import random  # noqa: PLC0415

    count = 0
    for business in Business.objects.filter(active=True).select_related("owner_persona"):
        try:
            fortune = random.randint(BUSINESS_FORTUNE_MIN, BUSINESS_FORTUNE_MAX)  # noqa: S311
            run_business_week(business, fortune=fortune)
            count += 1
        except Exception:
            logger.exception("weekly economy: business %s failed", business.pk)
    return count
