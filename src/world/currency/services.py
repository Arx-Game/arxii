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
from django.db import models, transaction
from django.utils import timezone

from world.currency.constants import (
    ACTIVE_WEEK_LOGIN_DAYS,
    ALLOWANCE_SURPLUS_PCT,
    BUSINESS_BASE_WEEKLY_PER_LEVEL,
    BUSINESS_FORTUNE_MAX,
    BUSINESS_FORTUNE_MIN,
    CHORE_MULTIPLIER_CRIT,
    CHORE_MULTIPLIER_FAIL,
    CHORE_MULTIPLIER_SUCCESS,
    CONTRACT_DEFAULT_AFTER_MISSES,
    DEBT_PRINCIPAL_GROSS_PCT,
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
    FavorTokenDetails,
    IncomeDeclaration,
    OrganizationTreasury,
    OrgEconomicsProfile,
    OrgIncomeStream,
    OrgObligation,
)
from world.currency.types import (
    AllowanceResult,
    CollectionResult,
    DistributionResult,
    ImprovementResult,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from datetime import datetime

    from evennia.accounts.models import AccountDB

    from world.character_sheets.models import CharacterSheet
    from world.currency.models import DistinctionPurseDrain
    from world.items.models import ItemInstance
    from world.scenes.models import Persona
    from world.societies.models import Organization


def _account_active_since(account: AccountDB | None, cutoff: datetime) -> bool:
    """A piloted account counts as active when it logged in on/after ``cutoff`` (#929/#932)."""
    return account is not None and account.last_login is not None and account.last_login >= cutoff


def get_or_create_purse(character_sheet: CharacterSheet) -> CharacterPurse:
    purse, _ = CharacterPurse.objects.get_or_create(character_sheet=character_sheet)
    return purse


def get_or_create_treasury(organization: Organization) -> OrganizationTreasury:
    treasury, _ = OrganizationTreasury.objects.get_or_create(organization=organization)
    return treasury


def can_spend_treasury(treasury: OrganizationTreasury, persona: Persona) -> bool:
    """Spend authority: an active membership at tier <= spend_rank_max."""
    from world.societies.models import OrganizationMembership  # noqa: PLC0415

    return OrganizationMembership.objects.filter(
        persona=persona,
        organization_id=treasury.organization_id,
        left_at__isnull=True,
        exiled_at__isnull=True,
        rank__tier__lte=treasury.spend_rank_max,
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


def withdraw_from_treasury(
    *, organization: Organization, persona: Persona, amount: int, reason: str = ""
) -> CurrencyTransfer:
    """A spend-authorized member draws ``amount`` coppers from the org treasury to their purse.

    The discretionary-spend primitive for house distribution (#2540): the treasury→member
    outflow that #930 never built (every other treasury outflow is treasury→treasury). Gated by
    ``can_spend_treasury`` — an active membership at rank tier <= ``spend_rank_max`` (the head /
    top rank by default). Because it is action-driven it is inherently piloted-only; it must
    never be automated, so a non-piloted NPC head has no path to drain the coffers.

    Raises ``ValidationError`` if the persona lacks spend authority (or ``transfer`` rejects the
    amount / insufficient funds).
    """
    treasury = get_or_create_treasury(organization)
    if not can_spend_treasury(treasury, persona):
        msg = "You do not have the standing to spend from this treasury."
        raise ValidationError(msg)
    return transfer(
        amount=amount,
        reason=reason or f"treasury withdrawal by {persona}",
        from_treasury=treasury,
        to_purse=get_or_create_purse(persona.character_sheet),
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
    from world.items.services.materialize import materialize_item_game_object  # noqa: PLC0415

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
        # Coin is physical money (#1909): born as a real object in the
        # minter's inventory so it can be dropped/given/stowed/stolen.
        materialize_item_game_object(instance, holder_sheet)
    return instance


def _loose_cache_template():
    """Lazy ItemTemplate for loose-coin caches (same precedent as _instrument_template)."""
    from world.items.models import ItemTemplate  # noqa: PLC0415

    template, _ = ItemTemplate.objects.get_or_create(
        name="Loose coins",
        defaults={"description": "PLACEHOLDER A handful of mixed coins."},
    )
    return template


def mint_loose_cache(
    *,
    amount: int,
    holder_sheet: CharacterSheet,
    from_purse: CharacterPurse | None = None,
    from_treasury: OrganizationTreasury | None = None,
) -> ItemInstance:
    """Convert ledger money into a loose-coin cache item (#1909).

    Unlike ``mint_instrument`` the face value is arbitrary and there is NO
    mint fee — this is everyday cash, not a grand instrument. Value is
    conserved: it leaves the ledger and lives in the item until redemption
    (``redeem_instrument`` handles deposit unchanged — it is face_value-driven).
    """
    from world.currency.constants import Denomination  # noqa: PLC0415
    from world.items.models import ItemInstance  # noqa: PLC0415
    from world.items.services.materialize import materialize_item_game_object  # noqa: PLC0415

    with transaction.atomic():
        transfer(
            amount=amount,
            reason="withdraw loose coins",
            from_purse=from_purse,
            from_treasury=from_treasury,
        )
        instance = ItemInstance.objects.create(
            template=_loose_cache_template(),
            holder_character_sheet=holder_sheet,
        )
        CurrencyInstrumentDetails.objects.create(
            item_instance=instance,
            denomination=Denomination.LOOSE,
            face_value=amount,
        )
        # Coin is physical money (#1909): born as a real object in the
        # minter's inventory so it can be dropped/given/stowed/stolen.
        materialize_item_game_object(instance, holder_sheet)
    return instance


def redeem_instrument(
    *,
    instance: ItemInstance,
    to_purse: CharacterPurse | None = None,
    to_treasury: OrganizationTreasury | None = None,
) -> CurrencyTransfer:
    """Convert a physical coin back into ledger money (fee-free).

    Consumes the instrument (the coin is melted back into the books) —
    including its physical ObjectDB, when one exists, via the established
    consumption pattern (``usage.hard_delete_item_instance`` precedent:
    delete the game_object, CASCADE removes the ItemInstance row; ownership
    events survive via SET_NULL). Without this a redeemed coin would linger
    as a ghost object in the depositor's inventory (#1909).
    """
    details = CurrencyInstrumentDetails.objects.get(item_instance=instance)
    with transaction.atomic():
        row = transfer(
            amount=details.face_value,
            reason=f"redeem {details.denomination}",
            to_purse=to_purse,
            to_treasury=to_treasury,
        )
        game_object = instance.game_object
        holder = game_object.location if game_object is not None else None
        if game_object is not None:
            game_object.delete()  # CASCADE removes the ItemInstance row
        else:
            instance.delete()
        if holder is not None and hasattr(holder, "carried_items"):
            holder.carried_items.invalidate()
    return row


def _favor_token_template():
    """Lazy ItemTemplate for Golden Hares (same precedent as ``_instrument_template``).

    PLACEHOLDER description — Golden Hare flavor text is an authored-content
    pass for Apostate.
    """
    from world.items.models import ItemTemplate  # noqa: PLC0415

    template, _ = ItemTemplate.objects.get_or_create(
        name="Golden Hare",
        defaults={
            "description": (
                "PLACEHOLDER A gold coin stamped with a hare whose eyes are two "
                "flecks of emerald. One deed done, waiting to be called in."
            ),
        },
    )
    return template


def mint_favor_token(
    org: Organization,
    recipient_character: CharacterSheet,
    *,
    provenance_note: str,
) -> FavorTokenDetails:
    """Mint a Golden Hare: one deed done for ``org``, now a physical coin (#2428).

    Mirrors ``mint_instrument``'s item-creation shape, but favor tokens are
    NOT coppers-denominated — no ledger transfer, no mint fee involved. A
    Hare is deed-backed, not money-backed; ordinary item give/trade already
    moves it once minted (no market machinery).
    """
    from world.items.models import ItemInstance  # noqa: PLC0415
    from world.items.services.materialize import materialize_item_game_object  # noqa: PLC0415

    with transaction.atomic():
        instance = ItemInstance.objects.create(
            template=_favor_token_template(),
            holder_character_sheet=recipient_character,
        )
        token = FavorTokenDetails.objects.create(
            item_instance=instance,
            issuing_organization=org,
            provenance_note=provenance_note,
        )
        # Coin is physical (#1909 precedent): born as a real object in the
        # recipient's inventory so it can be dropped/given/stowed/stolen/traded.
        materialize_item_game_object(instance, recipient_character)
    return token


def redeem_favor_token(token: FavorTokenDetails, *, redeemer_org: Organization) -> None:
    """Surrender a Golden Hare: the deed is called in, once (#2428).

    Only the issuing organization can redeem its own Hare — trading a Hare
    changes who carries it, never who it is owed to. Deed-provenance is
    story-significant (never hard-deleted, per CLAUDE.md): mirrors the
    items app's soft-delete norm (``consume_item_charges``'s preserve
    branch, ``forfeit_item_instance``) rather than ``redeem_instrument``'s
    hard-delete — stamps ``ItemInstance.destroyed_at`` and relocates the
    game_object out of play, but keeps both the ``ItemInstance`` and this
    ``FavorTokenDetails`` row as history; only ``redeemed_at`` flips.

    Raises ``ValidationError`` if already redeemed or if ``redeemer_org`` is
    not the Hare's issuer.
    """
    from world.items.constants import OwnershipEventType  # noqa: PLC0415
    from world.items.models import ItemInstance, OwnershipEvent  # noqa: PLC0415

    with transaction.atomic():
        locked = FavorTokenDetails.objects.select_for_update().get(pk=token.pk)
        if locked.redeemed_at is not None:
            msg = "This Golden Hare has already been redeemed."
            raise ValidationError(msg)
        if locked.issuing_organization_id != redeemer_org.pk:
            msg = "Only the issuing organization can redeem this Golden Hare."
            raise ValidationError(msg)
        item = ItemInstance.objects.select_for_update().get(pk=locked.item_instance_id)
        holder_sheet = item.holder_character_sheet
        now = timezone.now()
        item.destroyed_at = now
        item.save(update_fields=["destroyed_at"])
        game_object = item.game_object
        holder = game_object.location if game_object is not None else None
        if game_object is not None:
            # Relocate-but-not-delete (mirrors the soft-delete branch): the
            # coin leaves play but its row — and this detail row — survive
            # as deed-provenance.
            game_object.location = None
            game_object.save()
        if holder is not None and hasattr(holder, "carried_items"):
            holder.carried_items.invalidate()
        OwnershipEvent.objects.create(
            item_instance=item,
            event_type=OwnershipEventType.CONSUMED,
            from_character_sheet=holder_sheet,
            notes=f"Redeemed with {redeemer_org.name}.",
        )
        locked.redeemed_at = now
        locked.save(update_fields=["redeemed_at"])


def get_or_create_economics(organization: Organization) -> OrgEconomicsProfile:
    economics, _ = OrgEconomicsProfile.objects.get_or_create(organization=organization)
    return economics


@transaction.atomic
def accrue_income_stream(stream: OrgIncomeStream) -> int:
    """One weekly cycle: the gross amasses in the uncollected pool (#930).

    No treasury transfer, no declaration — income never lands passively
    (ADR-0081). No cap either: an idle org's pool grows unusably while a
    hoarded pool concentrates collection risk. Returns the new pool value.
    Plain add, not F() — SharedMemoryModel instances must never hold a
    CombinedExpression.
    """
    if not stream.active:
        msg = "This income stream is inactive."
        raise ValidationError(msg)
    gross = stream.gross_amount
    # A domain holding's yield rides its domain's prosperity (#2238): a thriving
    # domain amasses more per cycle, a collapsed one (prosperity 0) nothing.
    # ``domain_holding`` is the reverse OneToOne — absent for non-domain streams.
    holding = stream.domain_holding_or_none
    if holding is not None:
        gross = int(gross * holding.domain.income_multiplier)
    stream.uncollected_pool = stream.uncollected_pool + gross
    stream.save(update_fields=["uncollected_pool"])
    return stream.uncollected_pool


def process_income_stream(
    stream: OrgIncomeStream,
    amount: int,
    *,
    declared_amount: int | None = None,
) -> IncomeDeclaration:
    """Land ``amount`` collected coppers from one stream (#926, reshaped by #930).

    ``amount`` is this stream's share of a collection dispatch's landed
    aggregate — graft has already leaked off upstream (it hits the collected
    aggregate, not the weekly gross). The net mints into the org treasury via
    the audited transfer path; debt service and garnishments withhold at the
    source; an IncomeDeclaration records actual-vs-declared for obligation
    settlement. ``declared_amount`` defaults to the honest number —
    under-declaring is a deliberate caller action with discovery consequences.
    """
    if not stream.active:
        msg = "This income stream is inactive."
        raise ValidationError(msg)

    treasury = get_or_create_treasury(stream.organization)
    if amount > 0:
        transfer(
            amount=amount,
            reason=f"income: {stream.name}",
            to_treasury=treasury,
        )

    # Backstop only (#930): creditors normally collect at source from the
    # pools each week; this catches arrears the pools couldn't cover, biting
    # the landed amount before the money is "yours" (#927).
    _withhold_debt_service(stream, treasury, amount)

    declared = amount if declared_amount is None else declared_amount
    return IncomeDeclaration.objects.create(
        stream=stream,
        actual_amount=amount,
        declared_amount=declared,
    )


def _collection_band_pct(success_level: int) -> int | None:
    """Percent of the gathered pool that lands for this band; None = catastrophe."""
    from world.currency.constants import COLLECTION_BAND_PCTS  # noqa: PLC0415

    for floor, pct in COLLECTION_BAND_PCTS:
        if success_level >= floor:
            return pct
    return None


@transaction.atomic
def collect_org_income(*, organization: Organization, character) -> CollectionResult:
    """One active collection dispatch across every pooled stream of ``organization`` (#930).

    The collector gathers the org's whole uncollected aggregate (pools zero
    the moment the attempt happens — the money left with the collector), then
    a Tax Collection check decides how much arrives: the outcome band scales
    the aggregate, graft leaks its percentage off the *collected* amount, and
    the net rides the per-stream landing path (debt withholding, garnishment,
    declarations) proportionally to each stream's share. Catastrophe lands
    nothing — the pool is simply gone, and the collector-incident encounter is
    a combat-domain follow-up seam. Collector competence is a flat PLACEHOLDER
    input until improvable agent stats (#672) exist; the streams' ``area`` FK
    is authored data for a future local order/crime difficulty modifier (the
    locations cascade reads rooms, not bare areas — deliberately not rebuilt
    here).
    """
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.checks.services import perform_check  # noqa: PLC0415
    from world.currency.constants import TAX_COLLECTION_CHECK_NAME  # noqa: PLC0415
    from world.scenes.action_constants import DIFFICULTY_VALUES, DifficultyChoice  # noqa: PLC0415

    streams = list(
        OrgIncomeStream.objects.filter(
            organization=organization, active=True, uncollected_pool__gt=0
        )
    )
    # #1826 — a lying-low member's rackets run short-handed: CRIME_KICKUP
    # pools in that area are docked before the gather (the take never existed).
    from world.currency.constants import IncomeStreamKind  # noqa: PLC0415
    from world.justice.constants import LIE_LOW_CRIME_MALUS_PCT  # noqa: PLC0415
    from world.justice.lifecycle import crime_collection_malus_applies  # noqa: PLC0415

    for stream in streams:
        if stream.kind == IncomeStreamKind.CRIME_KICKUP and crime_collection_malus_applies(
            organization, stream.area
        ):
            stream.uncollected_pool -= stream.uncollected_pool * LIE_LOW_CRIME_MALUS_PCT // 100
    gathered = sum(stream.uncollected_pool for stream in streams)
    # Gems ride the same dispatch (Build 0b): a mine may have accrued gems but no coin,
    # so the empty-gate must consider the org's pending gem pools too.
    from world.items.gems.collection import (  # noqa: PLC0415
        collect_org_gems,
        org_has_pending_gems,
    )

    has_gems = org_has_pending_gems(organization)
    if gathered <= 0 and not has_gems:
        msg = "There is nothing waiting to be collected."
        raise ValidationError(msg)
    shares = {stream.pk: stream.uncollected_pool for stream in streams}
    for stream in streams:
        stream.uncollected_pool = 0
        stream.save(update_fields=["uncollected_pool"])

    check_type = CheckType.objects.filter(name__iexact=TAX_COLLECTION_CHECK_NAME).first()
    success_level = 0  # unseeded world: every collection is an unremarkable partial
    if check_type is not None:
        result = perform_check(
            character,
            check_type,
            target_difficulty=DIFFICULTY_VALUES[DifficultyChoice.NORMAL],
        )
        success_level = result.success_level

    collector_sheet = character.character_sheet
    economics = get_or_create_economics(organization)
    pct = _collection_band_pct(success_level)
    if pct is None:
        # Catastrophe: the collector never made it back — coin and gems alike are gone.
        gems = collect_org_gems(
            organization=organization,
            collector_sheet=collector_sheet,
            band_pct=None,
            graft_pct=economics.graft_pct,
        )
        return CollectionResult(
            gathered=gathered,
            landed=0,
            graft_leak=0,
            success_level=success_level,
            catastrophe=True,
            stones_lost=gems.stones_lost,
        )

    collected = gathered * pct // 100
    graft_leak = collected * economics.graft_pct // 100
    net = collected - graft_leak

    # Land per stream, proportional to each pool's share of the gather, so
    # declarations/obligations stay per-stream. Remainder rides the last row.
    landed_total = 0
    for index, stream in enumerate(streams):
        if index < len(streams) - 1:
            share = net * shares[stream.pk] // gathered
        else:
            share = net - landed_total
        landed_total += share
        process_income_stream(stream, share)

    # Gems ride the same band + graft into the house stock / the collector's hands.
    gems = collect_org_gems(
        organization=organization,
        collector_sheet=collector_sheet,
        band_pct=pct,
        graft_pct=economics.graft_pct,
    )
    return CollectionResult(
        gathered=gathered,
        landed=net,
        graft_leak=graft_leak,
        success_level=success_level,
        gem_value_landed=gems.common_value_landed,
        stones_delivered=gems.stones_delivered,
        stones_lost=gems.stones_lost,
    )


@transaction.atomic
def distribute_allowance(*, organization: Organization, surplus: int) -> AllowanceResult:
    """Auto-split a share of ``surplus`` among the org's active piloted members (#2540).

    The **non-discretionary allowance** rail — the head cannot withhold it. Meant to fire off the
    collection event (the future domain dispatch calls ``collect_org_income`` then this with the
    net as ``surplus``), so the baseline reaches players without anyone having to coerce the head.
    A PLACEHOLDER share (``ALLOWANCE_SURPLUS_PCT``) of surplus splits equally among members whose
    account logged in within ``ACTIVE_WEEK_LOGIN_DAYS`` — pure NPCs have no ``db_account`` and are
    excluded for free, and a member is paid once even across multiple member personas. Paid from
    the treasury (where the collected surplus sits); the pool is capped at the treasury balance so
    it never overdraws. Whole-copper division; the remainder simply stays in the treasury.
    """
    from world.societies.models import OrganizationMembership  # noqa: PLC0415

    if surplus <= 0:
        return AllowanceResult(total_distributed=0, per_member=0, member_count=0)
    treasury = get_or_create_treasury(organization)
    # Read the balance under the same row lock the transfers below take, so a concurrent
    # withdrawal can't shrink it between the pool cap and the payouts (which would abort
    # the whole distribution instead of distributing the smaller pool).
    treasury = OrganizationTreasury.objects.select_for_update().get(pk=treasury.pk)
    pool = min(surplus * ALLOWANCE_SURPLUS_PCT // 100, treasury.balance)
    if pool <= 0:
        return AllowanceResult(total_distributed=0, per_member=0, member_count=0)

    cutoff = timezone.now() - timedelta(days=ACTIVE_WEEK_LOGIN_DAYS)
    active_sheets: dict[int, CharacterSheet] = {}
    memberships = OrganizationMembership.objects.filter(
        organization=organization, left_at__isnull=True, exiled_at__isnull=True
    ).select_related("persona__character_sheet__character__db_account")
    for membership in memberships:
        sheet = membership.persona.character_sheet
        if sheet is None or sheet.pk in active_sheets:
            continue
        if _account_active_since(sheet.character.db_account, cutoff):
            active_sheets[sheet.pk] = sheet
    if not active_sheets:
        return AllowanceResult(total_distributed=0, per_member=0, member_count=0)

    per_member = pool // len(active_sheets)
    if per_member <= 0:
        return AllowanceResult(total_distributed=0, per_member=0, member_count=len(active_sheets))
    distributed = 0
    for sheet in active_sheets.values():
        transfer(
            amount=per_member,
            reason="house allowance",
            from_treasury=treasury,
            to_purse=get_or_create_purse(sheet),
        )
        distributed += per_member
    return AllowanceResult(
        total_distributed=distributed, per_member=per_member, member_count=len(active_sheets)
    )


@transaction.atomic
def service_debt_principal(*, organization: Organization, basis: int) -> int:
    """Pay a flat share of ``basis`` (the collection's gross) toward debt principal.

    The debt-first leg of the distribution dispatch (#2540, ruled 2026-07-20): a
    mandatory ``DEBT_PRINCIPAL_GROSS_PCT`` of gross goes to creditors BEFORE the member
    allowance draws anything — like an allowance the head cannot withhold, owed to the
    bank instead of the members. Complements the weekly at-source ARREARS withholding
    (#927 — interest); this pays PRINCIPAL, oldest debt first (PLACEHOLDER ordering),
    capped by each principal and the treasury balance. ``diverting`` debts are skipped
    (the cheat routes income past servicing — arrears balloon, discovery is story).
    A debt paid to zero deactivates. Returns the total coppers paid.
    """
    target = basis * DEBT_PRINCIPAL_GROSS_PCT // 100
    if target <= 0:
        return 0
    treasury = get_or_create_treasury(organization)
    paid_total = 0
    debts = DebtInstrument.objects.filter(
        debtor_organization=organization, active=True, diverting=False, principal__gt=0
    ).order_by("created_at")
    for debt in debts:
        if paid_total >= target:
            break
        treasury.refresh_from_db(fields=["balance"])
        payment = min(target - paid_total, debt.principal, treasury.balance)
        if payment <= 0:
            break
        transfer(
            amount=payment,
            reason=f"debt principal: {debt.creditor_organization.name}",
            from_treasury=treasury,
            to_treasury=get_or_create_treasury(debt.creditor_organization),
        )
        debt.principal -= payment
        if debt.principal == 0:
            debt.active = False
        debt.save(update_fields=["principal", "active"])
        paid_total += payment
    return paid_total


def collect_and_distribute(*, organization: Organization, character) -> DistributionResult:
    """The full collection-distribution dispatch (#2540, ruled 2026-07-20).

    Sequence: ``collect_org_income`` (the active piloted collection — band, graft,
    catastrophe, gems all as before) → ``service_debt_principal`` (the mandatory
    debt-first share of GROSS) → ``distribute_allowance`` on the post-debt remainder
    of what actually landed. Each phase is independently atomic (a later phase's
    failure never claws back an earlier one, mirroring ``run_weekly_economy``); the
    remainder after the allowance simply stays in the treasury.
    """
    collection = collect_org_income(organization=organization, character=character)
    # A catastrophe landed nothing — this collection funds no debt service (old treasury
    # funds are not clawed; the creditor's share rides actual collections only).
    basis = 0 if collection.catastrophe else collection.gathered
    debt_paid = service_debt_principal(organization=organization, basis=basis)
    surplus = max(0, collection.landed - debt_paid)
    allowance = distribute_allowance(organization=organization, surplus=surplus)
    return DistributionResult(
        collection=collection, debt_principal_paid=debt_paid, allowance=allowance
    )


@transaction.atomic
def collect_asset_income(*, asset, character_sheet) -> CollectionResult:
    """One active collection of a personal asset's accumulated income (#2294).

    Mirrors ``collect_org_income`` but for a single NPCAsset's pool: zeros
    the pool (the money left with the collector), rolls a Tax Collection
    check, applies the outcome band, and lands the net in the collector's
    CharacterPurse via ``transfer`` (null source = mint). No graft — graft
    is an org-level corruption concept that doesn't apply to a personal
    asset. Catastrophe loses the entire pool.

    Args:
        asset: The NPCAsset whose ``uncollected_pool`` is being collected.
        character_sheet: The CharacterSheet of the PC collecting.

    Returns:
        CollectionResult with gathered, landed, and catastrophe info.

    Raises:
        ValidationError: If the pool is empty (nothing to collect).
    """
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.checks.services import perform_check  # noqa: PLC0415
    from world.currency.constants import TAX_COLLECTION_CHECK_NAME  # noqa: PLC0415
    from world.scenes.action_constants import (  # noqa: PLC0415
        DIFFICULTY_VALUES,
        DifficultyChoice,
    )

    gathered = asset.uncollected_pool
    if gathered <= 0:
        msg = "There is nothing waiting to be collected."
        raise ValidationError(msg)
    asset.uncollected_pool = 0
    asset.save(update_fields=["uncollected_pool"])

    check_type = CheckType.objects.filter(name__iexact=TAX_COLLECTION_CHECK_NAME).first()
    success_level = 0  # unseeded world: every collection is an unremarkable partial
    if check_type is not None:
        result = perform_check(
            character_sheet.character,
            check_type,
            target_difficulty=DIFFICULTY_VALUES[DifficultyChoice.NORMAL],
        )
        success_level = result.success_level

    pct = _collection_band_pct(success_level)
    if pct is None:
        # Catastrophe: the money never made it to the collector.
        return CollectionResult(
            gathered=gathered, landed=0, graft_leak=0, success_level=success_level, catastrophe=True
        )

    net = gathered * pct // 100
    if net > 0:
        transfer(
            amount=net,
            reason="asset income collection",
            to_purse=get_or_create_purse(character_sheet),
        )
    return CollectionResult(
        gathered=gathered, landed=net, graft_leak=0, success_level=success_level
    )


@transaction.atomic
def improve_org_domain(*, organization: Organization, character) -> ImprovementResult:
    """One domain-investment attempt (#930): Scholarship/Economics against the ledgers.

    Success raises every active stream's gross by ``IMPROVEMENT_GROSS_PCT``
    percent AND cracks graft down a step; a partial success only manages the
    crackdown; failure changes nothing (backfire texture is a later pass).
    All magnitudes PLACEHOLDER.
    """
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.checks.services import perform_check  # noqa: PLC0415
    from world.currency.constants import (  # noqa: PLC0415
        DOMAIN_INVESTMENT_CHECK_NAME,
        IMPROVEMENT_GRAFT_STEP,
        IMPROVEMENT_GROSS_PCT,
    )
    from world.scenes.action_constants import DIFFICULTY_VALUES, DifficultyChoice  # noqa: PLC0415

    check_type = CheckType.objects.filter(name__iexact=DOMAIN_INVESTMENT_CHECK_NAME).first()
    success_level = -1  # unseeded world: investment simply fails, nothing moves
    if check_type is not None:
        result = perform_check(
            character,
            check_type,
            target_difficulty=DIFFICULTY_VALUES[DifficultyChoice.NORMAL],
        )
        success_level = result.success_level

    economics = get_or_create_economics(organization)
    gross_raised = False
    graft_cracked = False
    if success_level >= 0:
        new_graft = max(GRAFT_FLOOR_PCT, economics.graft_pct - IMPROVEMENT_GRAFT_STEP)
        graft_cracked = new_graft != economics.graft_pct
        economics.graft_pct = new_graft
        economics.save(update_fields=["graft_pct"])
    if success_level >= 1:
        for stream in OrgIncomeStream.objects.filter(organization=organization, active=True):
            bump = stream.gross_amount * IMPROVEMENT_GROSS_PCT // 100
            if bump > 0:
                stream.gross_amount = stream.gross_amount + bump
                stream.save(update_fields=["gross_amount"])
                gross_raised = True
    return ImprovementResult(
        success_level=success_level,
        gross_raised=gross_raised,
        graft_cracked=graft_cracked,
        new_graft_pct=economics.graft_pct,
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


def _service_debts_from_pools(organization: Organization) -> int:
    """Weekly at-source debt service (#930): the creditor collects from the pools.

    Apostate's asymmetry rule: automatic LOSS is fine, automatic gain is not —
    so while income never lands passively (ADR-0081), contractual debt service
    deducts from the amassing pools every cycle without the debtor lifting a
    finger. Oldest debt first, capped at what the pools hold (over-leverage
    bottoms at empty pools, never seizure); ``diverting`` debts are skipped —
    that money pools whole, the arrears keep growing, and discovery stays the
    player-facing risk loop. Pool money is off-ledger, so the creditor-side
    transfer is mint-shaped (the same way landing mints at collection).
    Returns coppers serviced.
    """
    debts = list(
        DebtInstrument.objects.filter(
            debtor_organization=organization,
            active=True,
            diverting=False,
            arrears__gt=0,
        ).order_by("created_at")
    )
    if not debts:
        return 0
    streams = list(
        OrgIncomeStream.objects.filter(
            organization=organization, active=True, uncollected_pool__gt=0
        )
    )
    available = sum(stream.uncollected_pool for stream in streams)
    if available <= 0:
        return 0
    paid_total = 0
    for debt in debts:
        if available <= 0:
            break
        payment = min(debt.arrears, available)
        transfer(
            amount=payment,
            reason=f"debt service at source: {debt.creditor_organization.name}",
            to_treasury=get_or_create_treasury(debt.creditor_organization),
        )
        debt.arrears -= payment
        debt.save(update_fields=["arrears"])
        available -= payment
        paid_total += payment
    remaining = paid_total
    for stream in streams:
        take = min(stream.uncollected_pool, remaining)
        if take > 0:
            stream.uncollected_pool = stream.uncollected_pool - take
            stream.save(update_fields=["uncollected_pool"])
            remaining -= take
        if remaining <= 0:
            break
    return paid_total


def _service_contract_liens_from_pools(organization: Organization) -> int:
    """Weekly at-source lien service (#930 unification of #928's garnishment).

    A defaulted notarized contract's lien (agreed at signing) takes its percent
    of the liened stream's fresh gross straight out of the pool — the same
    before-the-debtor-touches-it path as debt service. There is no separate
    landing-time garnishment machinery. Capped at what the pool holds.
    Returns coppers diverted.
    """
    diverted = 0
    liens = Contract.objects.filter(
        garnish_stream__organization=organization,
        status=ContractStatus.DEFAULTED,
        garnish_percent__gt=0,
    ).select_related("garnish_stream")
    for lien in liens:
        stream = lien.garnish_stream
        if not stream.active or stream.uncollected_pool <= 0:
            continue
        amount = min(stream.uncollected_pool, stream.gross_amount * lien.garnish_percent // 100)
        if amount <= 0:
            continue
        defaulter_is_proposer = lien.proposer_organization_id == stream.organization_id
        to_purse, to_treasury = _party_accounts(lien, proposer=not defaulter_is_proposer)
        transfer(
            amount=amount,
            reason=f"lien service at source: {lien.title}",
            to_purse=to_purse,
            to_treasury=to_treasury,
        )
        stream.uncollected_pool = stream.uncollected_pool - amount
        stream.save(update_fields=["uncollected_pool"])
        diverted += amount
    return diverted


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
    """The Sunday-rollover economy pass (#932, reshaped by #930). Per-phase counts.

    Order matters: interest accrues into arrears FIRST; then income streams
    pool their gross (never landing — ADR-0081); then at-source debt service
    deducts this week's arrears from the pools automatically (automatic loss
    is fine, automatic gain is not); then notarized contracts settle; then
    employment wages pay for actively-played weeks; then businesses roll
    their fortune. Each phase isolates failures per row — one broken org
    never wedges the rollover.
    """
    return {
        "interest": _weekly_interest_accrual(),
        "income": _weekly_income_streams(),
        "assets": _weekly_asset_income(),
        "debt_service": _weekly_debt_service(),
        "contracts": _weekly_contract_settlement(),
        "wages": _weekly_wages(),
        "businesses": _weekly_business_fortunes(),
    }


def _weekly_debt_service() -> int:
    """At-source creditor servicing for every owing org with pooled income (#930).

    One phase, one principle: debts AND defaulted-contract liens collect from
    the pools before the debtor can touch a copper.
    """
    count = 0
    debtor_ids = set(
        DebtInstrument.objects.filter(active=True, diverting=False, arrears__gt=0)
        .values_list("debtor_organization_id", flat=True)
        .distinct()
    )
    debtor_ids |= set(
        Contract.objects.filter(status=ContractStatus.DEFAULTED, garnish_percent__gt=0)
        .values_list("garnish_stream__organization_id", flat=True)
        .distinct()
    )
    from world.societies.models import Organization  # noqa: PLC0415

    for organization in Organization.objects.filter(pk__in=debtor_ids):
        try:
            serviced = _service_debts_from_pools(organization)
            serviced += _service_contract_liens_from_pools(organization)
            if serviced > 0:
                count += 1
        except Exception:
            logger.exception("weekly economy: debt service failed for org %s", organization.pk)
    return count


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
    # #930 / ADR-0081: the weekly cycle only amasses pools — money reaches a
    # treasury exclusively through an active collection dispatch.
    count = 0
    for stream in OrgIncomeStream.objects.filter(active=True).select_related("organization"):
        try:
            accrue_income_stream(stream)
            count += 1
        except Exception:
            logger.exception("weekly economy: income stream %s failed", stream.pk)
    return count


def _weekly_asset_income() -> int:
    """Accrue weekly income into each active asset's uncollected pool (#2294).

    Mirrors ``_weekly_income_streams`` for orgs: income amasses in the pool
    but never lands passively (ADR-0081). No cap — a hoarded pool
    concentrates collection risk.
    """
    from world.assets.constants import AssetStatus  # noqa: PLC0415
    from world.assets.models import NPCAsset  # noqa: PLC0415

    count = 0
    for asset in NPCAsset.objects.filter(status=AssetStatus.ACTIVE, weekly_income__gt=0):
        try:
            asset.uncollected_pool = asset.uncollected_pool + asset.weekly_income
            asset.save(update_fields=["uncollected_pool"])
            count += 1
        except Exception:
            logger.exception("weekly economy: asset income %s failed", asset.pk)
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
            run_weekly_employment(employment, was_active=_account_active_since(account, cutoff))
            count += 1
        except Exception:
            logger.exception("weekly economy: wages failed for employment %s", employment.pk)
    return count


def _weekly_business_fortunes() -> int:
    import random  # noqa: PLC0415

    rng = random.SystemRandom()
    count = 0
    for business in Business.objects.filter(active=True).select_related("owner_persona"):
        try:
            fortune = rng.randint(BUSINESS_FORTUNE_MIN, BUSINESS_FORTUNE_MAX)
            run_business_week(business, fortune=fortune)
            count += 1
        except Exception:
            logger.exception("weekly economy: business %s failed", business.pk)
    return count


@transaction.atomic
def deliver_mission_money(
    *,
    recipient_sheet: CharacterSheet,
    amount: int,
    ref: str,
    reason_label: str = "mission reward",
) -> None:
    """Reward money lands in the purse (#932 — replaces the Phase 5b stub).

    A mint (faucet) through the audited ledger; missions are a named
    faucet in the #923 inventory. ``reason_label`` keeps the ledger honest
    for non-mission callers (#1770 PR3 stake rewards pass "stake reward")
    without forking a parallel delivery function.
    """
    if amount <= 0:
        return
    transfer(
        amount=amount,
        reason=f"{reason_label}: {ref}"[:200],
        to_purse=get_or_create_purse(recipient_sheet),
    )


FAME_COPPERS_PER_POINT = 10


@transaction.atomic
def fund_fame_display(persona: Persona, *, amount: int) -> int:
    """Spend money maintaining fame against decay (#932 fame churn).

    The classic churn sink: fashion, events, displays — money leaves the
    world, fame_points rise at FAME_COPPERS_PER_POINT (calibration
    starting point), and the existing decay crons grind it back down.
    Returns fame points gained.
    """
    from world.societies.renown import set_persona_fame  # noqa: PLC0415

    if amount <= 0:
        msg = "Spend something to be seen."
        raise ValidationError(msg)
    points = amount // FAME_COPPERS_PER_POINT
    if points <= 0:
        msg = "Too little to make a splash."
        raise ValidationError(msg)
    transfer(
        amount=amount,
        reason="fame display",
        from_purse=get_or_create_purse(persona.character_sheet),
    )
    set_persona_fame(persona, persona.fame_points + points)
    return points


# --- Somehow Always Broke: weekly purse drain (#2613) ---

PURSE_DRAIN_REASON = "Somehow Always Broke weekly drain"


def snapshot_purse_drains() -> int:
    """SNAPSHOT band: record each drain-holder's opening balance (#2613).

    Runs *before* income lands, so the row captures the carried-over hoard
    the drain will target. Consumed later the same tick by ``run_purse_drains``
    in the DRAIN band. Idempotent per (holder, week): a re-run adds no rows.

    Returns the number of new snapshot rows written.
    """
    from world.currency.models import PurseDrainWeek  # noqa: PLC0415
    from world.distinctions.models import CharacterDistinction  # noqa: PLC0415
    from world.game_clock.week_services import get_current_game_week  # noqa: PLC0415

    # CharacterDistinction.character_id is the ObjectDB pk, which equals the
    # CharacterSheet pk (CharacterSheet.character is a primary_key O2O). Once
    # #2608 re-points that FK to CharacterSheet this becomes a direct field.
    holder_sheet_ids = list(
        CharacterDistinction.objects.filter(distinction__purse_drain__isnull=False).values_list(
            "character_id", flat=True
        )
    )
    if not holder_sheet_ids:
        return 0

    week = get_current_game_week()
    now = timezone.now()
    already = set(
        PurseDrainWeek.objects.filter(
            game_week=week, character_sheet_id__in=holder_sheet_ids
        ).values_list("character_sheet_id", flat=True)
    )
    purses = CharacterPurse.objects.filter(character_sheet_id__in=holder_sheet_ids)
    new_rows = [
        PurseDrainWeek(
            character_sheet_id=purse.character_sheet_id,
            game_week=week,
            opening_balance=purse.balance,
            snapshot_at=now,
        )
        for purse in purses
        if purse.character_sheet_id not in already
    ]
    PurseDrainWeek.objects.bulk_create(new_rows)
    return len(new_rows)


def _holder_drain_configs() -> dict[int, DistinctionPurseDrain]:
    """Map each drain-holder's sheet id to its strongest drain config (#2613).

    A holder with two drain distinctions (not a live scenario yet) resolves to
    the higher ``drain_percent`` so ordering is never arbitrary.
    """
    from world.distinctions.models import CharacterDistinction  # noqa: PLC0415

    configs: dict[int, DistinctionPurseDrain] = {}
    cds = CharacterDistinction.objects.filter(
        distinction__purse_drain__isnull=False
    ).select_related("distinction__purse_drain")
    for cd in cds:
        drain = cd.distinction.purse_drain
        current = configs.get(cd.character_id)
        if current is None or drain.drain_percent > current.drain_percent:
            configs[cd.character_id] = drain
    return configs


def run_purse_drains() -> int:
    """DRAIN band: empty each holder's purse down to this week's income (#2613).

    For opening balance ``S`` and outflows ``O`` since the snapshot (upkeep,
    dues, and ordinary spending alike — any outgoing cost), the drain removes
    ``clamp(S - O, 0, balance)`` scaled by ``drain_percent`` and never dips
    below ``floor_coppers``. Because the snapshot ran before income and this
    runs after obligations, the holder is left with exactly the week's fresh
    income (see ADR-0150 for the band ordering that makes that true).

    Every drain is an audited ``transfer`` sink, never a silent balance write.
    Per-row failure isolation: one broken holder never wedges the rest.

    Returns the number of holders actually drained (amount > 0).
    """
    from world.currency.models import PurseDrainWeek  # noqa: PLC0415
    from world.game_clock.week_services import get_current_game_week  # noqa: PLC0415
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
    from world.narrative.services import send_narrative_message  # noqa: PLC0415

    week = get_current_game_week()
    pending = list(
        PurseDrainWeek.objects.filter(game_week=week, drained_at__isnull=True).select_related(
            "character_sheet"
        )
    )
    if not pending:
        return 0

    configs = _holder_drain_configs()
    sheet_ids = [row.character_sheet_id for row in pending]
    purses = {
        purse.character_sheet_id: purse
        for purse in CharacterPurse.objects.filter(character_sheet_id__in=sheet_ids)
    }
    now = timezone.now()
    drained = 0

    for row in pending:
        try:
            config = configs.get(row.character_sheet_id)
            purse = purses.get(row.character_sheet_id)
            # Distinction removed between snapshot and drain, or no purse: close
            # the row without draining. Never drain against a stale snapshot.
            if config is None or purse is None or purse.balance == 0:
                row.drained_at = now
                row.save(update_fields=["drained_at"])
                continue

            outflows = (
                CurrencyTransfer.objects.filter(
                    from_purse=purse, created_at__gte=row.snapshot_at
                ).aggregate(total=models.Sum("amount"))["total"]
                or 0
            )
            drainable = min(max(0, row.opening_balance - outflows), purse.balance)
            amount = drainable * config.drain_percent // 100
            floor_room = max(0, purse.balance - config.floor_coppers)
            amount = min(amount, floor_room)

            row.outflows = outflows
            if amount > 0:
                transfer(amount=amount, reason=PURSE_DRAIN_REASON, from_purse=purse)
                row.amount_drained = amount
                send_narrative_message(
                    recipients=[row.character_sheet],
                    body=(
                        f"PLACEHOLDER: {format_coppers(amount)} has slipped through your "
                        "fingers again — gone by week's end, as it always is."
                    ),
                    category=NarrativeCategory.SYSTEM,
                )
                drained += 1
            row.drained_at = now
            row.save(update_fields=["outflows", "amount_drained", "drained_at"])
        except Exception:
            logger.exception("Purse drain failed for sheet %s", row.character_sheet_id)

    return drained
