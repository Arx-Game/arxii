"""Currency core (#925): formatting, transfers, authority, instruments."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.currency.constants import Denomination, format_coppers
from world.currency.models import CurrencyInstrumentDetails, CurrencyTransfer
from world.currency.services import (
    can_spend_treasury,
    get_or_create_purse,
    get_or_create_treasury,
    mint_instrument,
    redeem_instrument,
    transfer,
)
from world.scenes.factories import PersonaFactory


class FormatCoppersTests(TestCase):
    def test_mixed_form(self) -> None:
        assert format_coppers(1234) == "12g 3s 4c"

    def test_omits_zero_components(self) -> None:
        assert format_coppers(1200) == "12g"
        assert format_coppers(105) == "1g 5c"
        assert format_coppers(30) == "3s"

    def test_zero_and_negative(self) -> None:
        assert format_coppers(0) == "0c"
        assert format_coppers(-1234) == "-12g 3s 4c"


class TransferTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet_a = CharacterSheetFactory()
        cls.sheet_b = CharacterSheetFactory()

    def test_mint_and_purse_to_purse(self) -> None:
        purse_a = get_or_create_purse(self.sheet_a)
        purse_b = get_or_create_purse(self.sheet_b)
        transfer(amount=1000, reason="mission reward", to_purse=purse_a)
        purse_a.refresh_from_db()
        assert purse_a.balance == 1000

        transfer(amount=400, reason="payment", from_purse=purse_a, to_purse=purse_b)
        purse_a.refresh_from_db()
        purse_b.refresh_from_db()
        assert purse_a.balance == 600
        assert purse_b.balance == 400
        assert CurrencyTransfer.objects.count() == 2

    def test_sink_destroys_money(self) -> None:
        purse = get_or_create_purse(self.sheet_a)
        transfer(amount=500, reason="grant", to_purse=purse)
        transfer(amount=200, reason="guild fee", from_purse=purse)
        purse.refresh_from_db()
        assert purse.balance == 300

    def test_insufficient_funds(self) -> None:
        purse = get_or_create_purse(self.sheet_a)
        with self.assertRaises(ValidationError):
            transfer(amount=1, reason="overdraft", from_purse=purse)

    def test_void_and_nonpositive_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            transfer(amount=100, reason="void")
        purse = get_or_create_purse(self.sheet_a)
        with self.assertRaises(ValidationError):
            transfer(amount=0, reason="zero", to_purse=purse)


class TreasuryAuthorityTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from world.societies.factories import (
            OrganizationFactory,
            OrganizationMembershipFactory,
        )

        cls.org = OrganizationFactory()
        cls.treasury = get_or_create_treasury(cls.org)
        cls.leader = PersonaFactory()
        cls.grunt = PersonaFactory()
        OrganizationMembershipFactory(persona=cls.leader, organization=cls.org, rank=1)
        OrganizationMembershipFactory(persona=cls.grunt, organization=cls.org, rank=5)

    def test_rank_gate(self) -> None:
        assert can_spend_treasury(self.treasury, self.leader) is True
        assert can_spend_treasury(self.treasury, self.grunt) is False

    def test_outsider_cannot_spend(self) -> None:
        outsider = PersonaFactory()
        assert can_spend_treasury(self.treasury, outsider) is False


class InstrumentTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()

    def test_mint_charges_face_plus_fee_and_redeem_returns_face(self) -> None:
        purse = get_or_create_purse(self.sheet)
        face = 1_000  # Gold Knight = 10g = 1000c
        fee = 10  # 1%
        transfer(amount=face + fee, reason="grant", to_purse=purse)

        coin = mint_instrument(
            denomination=Denomination.GOLD_KNIGHT,
            holder_sheet=self.sheet,
            from_purse=purse,
        )
        purse.refresh_from_db()
        assert purse.balance == 0
        details = CurrencyInstrumentDetails.objects.get(item_instance=coin)
        assert details.face_value == face

        redeem_instrument(instance=coin, to_purse=purse)
        purse.refresh_from_db()
        assert purse.balance == face
        assert not CurrencyInstrumentDetails.objects.filter(pk=details.pk).exists()

    def test_mint_requires_funds(self) -> None:
        purse = get_or_create_purse(self.sheet)
        with self.assertRaises(ValidationError):
            mint_instrument(
                denomination=Denomination.GOLD_KNIGHT,
                holder_sheet=self.sheet,
                from_purse=purse,
            )
        assert CurrencyInstrumentDetails.objects.count() == 0


class OrgEconomicsTests(TestCase):
    """Income streams, Graft, declarations, obligations, contributions (#926)."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.societies.factories import OrganizationFactory

        cls.org = OrganizationFactory()
        cls.liege = OrganizationFactory()

    def test_income_leaks_graft_and_mints_net(self) -> None:
        from world.currency.models import OrgIncomeStream
        from world.currency.services import (
            get_or_create_economics,
            get_or_create_treasury,
            process_income_stream,
        )

        economics = get_or_create_economics(self.org)
        economics.graft_pct = 10
        economics.save()
        stream = OrgIncomeStream.objects.create(
            organization=self.org, name="Land taxes", kind="domain_tax", gross_amount=1000
        )

        declaration = process_income_stream(stream)

        treasury = get_or_create_treasury(self.org)
        treasury.refresh_from_db()
        assert treasury.balance == 900  # 10% leaked
        assert declaration.actual_amount == 900
        assert declaration.declared_amount == 900
        assert declaration.underdeclared is False

    def test_underdeclared_income_recorded(self) -> None:
        from world.currency.models import OrgIncomeStream
        from world.currency.services import process_income_stream

        stream = OrgIncomeStream.objects.create(
            organization=self.org, name="Turf kick-up", kind="crime_kickup", gross_amount=1000
        )
        declaration = process_income_stream(stream, declared_amount=300)
        assert declaration.underdeclared is True
        assert declaration.actual_amount == 900  # default graft 10%

    def test_obligations_compute_on_declared(self) -> None:
        from world.currency.models import OrgIncomeStream, OrgObligation
        from world.currency.services import (
            get_or_create_treasury,
            process_income_stream,
            settle_obligations,
        )

        stream = OrgIncomeStream.objects.create(
            organization=self.org, name="Land taxes", kind="domain_tax", gross_amount=1000
        )
        OrgObligation.objects.create(
            from_organization=self.org,
            to_organization=self.liege,
            name="Crown taxes",
            percent=20,
        )
        process_income_stream(stream, declared_amount=500)

        transfers = settle_obligations(self.org)

        assert len(transfers) == 1
        assert transfers[0].amount == 100  # 20% of DECLARED 500, not actual 900
        liege_treasury = get_or_create_treasury(self.liege)
        liege_treasury.refresh_from_db()
        assert liege_treasury.balance == 100

    def test_settlement_marks_declarations_and_is_idempotent(self) -> None:
        from world.currency.models import OrgIncomeStream, OrgObligation
        from world.currency.services import process_income_stream, settle_obligations

        stream = OrgIncomeStream.objects.create(
            organization=self.org, name="Land taxes", kind="domain_tax", gross_amount=1000
        )
        OrgObligation.objects.create(
            from_organization=self.org,
            to_organization=self.liege,
            name="Crown taxes",
            percent=20,
        )
        process_income_stream(stream)
        first = settle_obligations(self.org)
        second = settle_obligations(self.org)
        assert len(first) == 1
        assert second == []

    def test_contribution_moves_money_and_records(self) -> None:
        from world.currency.models import ContributionRecord
        from world.currency.services import (
            get_or_create_purse,
            get_or_create_treasury,
            record_contribution,
            transfer,
        )

        persona = PersonaFactory()
        purse = get_or_create_purse(persona.character_sheet)
        transfer(amount=500, reason="seed", to_purse=purse)

        record = record_contribution(
            persona=persona, organization=self.org, amount=200, reason="war chest"
        )

        purse.refresh_from_db()
        treasury = get_or_create_treasury(self.org)
        treasury.refresh_from_db()
        assert purse.balance == 300
        assert treasury.balance == 200
        assert record.transfer is not None
        assert ContributionRecord.objects.filter(organization=self.org).count() == 1

    def test_treat_servants_sinks_money_and_floors_graft(self) -> None:
        from django.core.exceptions import ValidationError as DjangoValidationError

        from world.currency.services import (
            get_or_create_economics,
            get_or_create_treasury,
            transfer,
            treat_servants,
        )

        treasury = get_or_create_treasury(self.org)
        transfer(amount=1000, reason="seed", to_treasury=treasury)
        economics = get_or_create_economics(self.org)
        economics.graft_pct = 5
        economics.save()

        result = treat_servants(self.org, payment=400, graft_reduction=10)

        treasury.refresh_from_db()
        assert treasury.balance == 600
        assert result.graft_pct == 1  # floored, never zero

        with self.assertRaises(DjangoValidationError):
            treat_servants(self.org, payment=100, graft_reduction=0)

    def test_inactive_stream_rejected(self) -> None:
        from django.core.exceptions import ValidationError as DjangoValidationError

        from world.currency.models import OrgIncomeStream
        from world.currency.services import process_income_stream

        stream = OrgIncomeStream.objects.create(
            organization=self.org,
            name="Dead stream",
            kind="domain_tax",
            gross_amount=100,
            active=False,
        )
        with self.assertRaises(DjangoValidationError):
            process_income_stream(stream)


class DebtTests(TestCase):
    """Debt as withholding at the income source (#927, per Apostate's model)."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.societies.factories import OrganizationFactory

        cls.debtor = OrganizationFactory()
        cls.blighton = OrganizationFactory()

    def _loan(self, **kwargs):
        from world.currency.services import extend_loan

        defaults = {
            "creditor": self.blighton,
            "debtor": self.debtor,
            "principal": 100_000,
            "fiat": True,
        }
        defaults.update(kwargs)
        return extend_loan(**defaults)

    def _drain_treasury(self):
        from world.currency.models import OrganizationTreasury

        OrganizationTreasury.objects.filter(organization=self.debtor).update(balance=0)
        OrganizationTreasury.flush_instance_cache()

    def _stream(self, gross=1000):
        from world.currency.models import OrgIncomeStream
        from world.currency.services import get_or_create_economics

        economics = get_or_create_economics(self.debtor)
        economics.graft_pct = 10
        economics.save()
        return OrgIncomeStream.objects.create(
            organization=self.debtor, name="Land taxes", kind="domain_tax", gross_amount=gross
        )

    def test_fiat_loan_mints_principal_to_debtor(self) -> None:
        from world.currency.services import get_or_create_treasury

        debt = self._loan()
        treasury = get_or_create_treasury(self.debtor)
        treasury.refresh_from_db()
        assert treasury.balance == 100_000
        assert debt.monthly_interest == 500  # 0.5% of 100k

    def test_interest_accrues_to_arrears_not_treasury(self) -> None:
        from world.currency.services import accrue_monthly_interest, get_or_create_treasury

        debt = self._loan()
        accrued = accrue_monthly_interest(self.debtor)

        debt.refresh_from_db()
        assert accrued == 500
        assert debt.arrears == 500
        treasury = get_or_create_treasury(self.debtor)
        treasury.refresh_from_db()
        assert treasury.balance == 100_000  # no money moved at accrual

    def test_income_withholds_debt_service_at_source(self) -> None:
        from world.currency.services import (
            accrue_monthly_interest,
            get_or_create_treasury,
            process_income_stream,
        )

        self._loan()
        self._drain_treasury()
        accrue_monthly_interest(self.debtor)
        stream = self._stream(gross=1000)

        process_income_stream(stream)  # net 900 after 10% graft

        debtor_treasury = get_or_create_treasury(self.debtor)
        debtor_treasury.refresh_from_db()
        creditor_treasury = get_or_create_treasury(self.blighton)
        creditor_treasury.refresh_from_db()
        assert creditor_treasury.balance == 500  # arrears paid first, at source
        assert debtor_treasury.balance == 400  # what reaches the books

    def test_overleveraged_income_bottoms_at_zero_never_seizes(self) -> None:
        from world.currency.models import DebtInstrument
        from world.currency.services import (
            accrue_monthly_interest,
            get_or_create_treasury,
            process_income_stream,
        )

        self._loan(principal=10_000_000)  # monthly interest 50_000
        self._drain_treasury()
        accrue_monthly_interest(self.debtor)
        stream = self._stream(gross=1000)

        process_income_stream(stream)  # net 900, all withheld

        debtor_treasury = get_or_create_treasury(self.debtor)
        debtor_treasury.refresh_from_db()
        assert debtor_treasury.balance == 0  # zero spendable income…
        debt = DebtInstrument.objects.get(debtor_organization=self.debtor)
        assert debt.arrears == 49_100  # …arrears persist, nothing seized
        assert debt.in_default is False  # and nothing defaults offscreen

    def test_diverting_skips_withholding_and_arrears_grow(self) -> None:
        from world.currency.services import (
            accrue_monthly_interest,
            get_or_create_treasury,
            process_income_stream,
        )

        debt = self._loan()
        debt.diverting = True
        debt.save()
        self._drain_treasury()
        accrue_monthly_interest(self.debtor)
        stream = self._stream(gross=1000)

        process_income_stream(stream)

        debtor_treasury = get_or_create_treasury(self.debtor)
        debtor_treasury.refresh_from_db()
        assert debtor_treasury.balance == 900  # the cheat: full income arrives
        debt.refresh_from_db()
        assert debt.arrears == 500  # the exposure: arrears untouched
        assert debt.in_default is False  # consequences are story, not bookkeeping

    def test_repay_principal_retires_debt(self) -> None:
        from django.core.exceptions import ValidationError as DjangoValidationError

        from world.currency.services import repay_principal

        debt = self._loan()  # debtor holds the 100k principal
        repay_principal(debt, 40_000)
        debt.refresh_from_db()
        assert debt.principal == 60_000
        assert debt.active is True

        repay_principal(debt, 60_000)
        debt.refresh_from_db()
        assert debt.principal == 0
        assert debt.active is False

        with self.assertRaises(DjangoValidationError):
            repay_principal(debt, 1)


class ContractTests(TestCase):
    """Consent-gated contracts, settlement, defaults, garnishment (#928)."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.societies.factories import OrganizationFactory

        cls.org = OrganizationFactory()
        cls.notary = OrganizationFactory()
        cls.payee = PersonaFactory()

    def _contract(self, **kwargs):
        from world.currency.models import Contract

        defaults = {
            "proposer_organization": self.org,
            "counterparty_persona": self.payee,
            "title": "Stipend",
            "terms": "100c per cycle, garnish on default",
            "formality": "notarized",
            "notary_organization": self.notary,
        }
        defaults.update(kwargs)
        return Contract.objects.create(**defaults)

    def _fund_org(self, amount):
        from world.currency.services import get_or_create_treasury, transfer

        treasury = get_or_create_treasury(self.org)
        transfer(amount=amount, reason="seed", to_treasury=treasury)
        return treasury

    def test_signing_is_consent_and_charges_notary_fee(self) -> None:
        from world.currency.constants import NOTARY_FEE_COPPERS
        from world.currency.services import sign_contract

        treasury = self._fund_org(5_000)
        contract = self._contract()
        sign_contract(contract)

        contract.refresh_from_db()
        treasury.refresh_from_db()
        assert contract.status == "active"
        assert contract.signed_at is not None
        assert treasury.balance == 5_000 - NOTARY_FEE_COPPERS

    def test_notarized_requires_notary(self) -> None:
        from django.core.exceptions import ValidationError as DjangoValidationError

        from world.currency.services import sign_contract

        self._fund_org(5_000)
        contract = self._contract(notary_organization=None)
        with self.assertRaises(DjangoValidationError):
            sign_contract(contract)

    def test_handshake_signs_free_but_never_settles(self) -> None:
        from django.core.exceptions import ValidationError as DjangoValidationError

        from world.currency.services import settle_contract_cycle, sign_contract

        contract = self._contract(formality="handshake", notary_organization=None)
        sign_contract(contract)
        contract.refresh_from_db()
        assert contract.status == "active"
        with self.assertRaises(DjangoValidationError):
            settle_contract_cycle(contract)

    def test_recurring_settlement_pays_each_cycle(self) -> None:
        from world.currency.models import ContractTerm
        from world.currency.services import (
            get_or_create_purse,
            settle_contract_cycle,
            sign_contract,
        )

        self._fund_org(10_000)
        contract = self._contract()
        ContractTerm.objects.create(
            contract=contract, payer_is_proposer=True, amount=100, recurring=True
        )
        sign_contract(contract)

        settle_contract_cycle(contract)
        settle_contract_cycle(contract)

        purse = get_or_create_purse(self.payee.character_sheet)
        purse.refresh_from_db()
        assert purse.balance == 200
        contract.refresh_from_db()
        assert contract.status == "active"  # recurring never auto-completes

    def test_oneshot_completes_contract(self) -> None:
        from world.currency.models import ContractTerm
        from world.currency.services import settle_contract_cycle, sign_contract

        self._fund_org(10_000)
        contract = self._contract(title="Ransom payment")
        ContractTerm.objects.create(
            contract=contract, payer_is_proposer=True, amount=2_000, recurring=False
        )
        sign_contract(contract)
        settle_contract_cycle(contract)

        contract.refresh_from_db()
        assert contract.status == "completed"

    def test_two_missed_cycles_default_then_garnishment(self) -> None:
        from world.currency.models import ContractTerm, OrganizationTreasury, OrgIncomeStream
        from world.currency.services import (
            get_or_create_purse,
            process_income_stream,
            settle_contract_cycle,
            sign_contract,
        )

        self._fund_org(1_000)  # just enough for the notary fee
        stream = OrgIncomeStream.objects.create(
            organization=self.org, name="Land taxes", kind="domain_tax", gross_amount=1000
        )
        contract = self._contract(garnish_stream=stream, garnish_percent=50)
        ContractTerm.objects.create(
            contract=contract, payer_is_proposer=True, amount=5_000, recurring=True
        )
        sign_contract(contract)  # spends the 1000 on the fee; org is broke

        settle_contract_cycle(contract)
        contract.refresh_from_db()
        assert contract.status == "active"
        assert contract.consecutive_missed == 1

        settle_contract_cycle(contract)
        contract.refresh_from_db()
        assert contract.status == "defaulted"

        # Default activates the agreed lien: half the stream's net diverts.
        OrganizationTreasury.flush_instance_cache()
        process_income_stream(stream)  # default graft 10% → net 900
        purse = get_or_create_purse(self.payee.character_sheet)
        purse.refresh_from_db()
        assert purse.balance == 450  # 50% of 900

    def test_garnishment_inert_before_default(self) -> None:
        from world.currency.models import ContractTerm, OrgIncomeStream
        from world.currency.services import (
            get_or_create_purse,
            process_income_stream,
            sign_contract,
        )

        self._fund_org(10_000)
        stream = OrgIncomeStream.objects.create(
            organization=self.org, name="Land taxes", kind="domain_tax", gross_amount=1000
        )
        contract = self._contract(garnish_stream=stream, garnish_percent=50)
        ContractTerm.objects.create(
            contract=contract, payer_is_proposer=True, amount=100, recurring=True
        )
        sign_contract(contract)

        process_income_stream(stream)

        purse = get_or_create_purse(self.payee.character_sheet)
        purse.refresh_from_db()
        assert purse.balance == 0  # agreed lien, but no default — no enforcement


class ProfessionTests(TestCase):
    """AP-locked wages and chore checks (#929)."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.currency.models import CharacterEmployment, Profession

        cls.persona = PersonaFactory()
        cls.sheet = cls.persona.character_sheet
        cls.profession = Profession.objects.create(
            name="Dockhand", wage_per_ap=10, ap_reservation_weekly=40
        )
        cls.employment = CharacterEmployment.objects.create(
            character_sheet=cls.sheet, profession=cls.profession
        )

    def _pool(self, current=200):
        from world.action_points.models import ActionPointPool

        pool = ActionPointPool.get_or_create_for_character(self.sheet.character)
        ActionPointPool.objects.filter(pk=pool.pk).update(current=current)
        ActionPointPool.flush_instance_cache()
        return pool

    def test_weekly_wages_lock_ap_and_pay(self) -> None:
        from world.action_points.models import ActionPointPool
        from world.currency.services import get_or_create_purse, run_weekly_employment

        self._pool(200)
        paid = run_weekly_employment(self.employment, was_active=True)

        assert paid == 400  # 40 AP × 10c = 4 silver... = 4g/wk at weekly scale
        pool = ActionPointPool.get_or_create_for_character(self.sheet.character)
        assert pool.current == 160  # the week's allotment is gone
        purse = get_or_create_purse(self.sheet)
        purse.refresh_from_db()
        assert purse.balance == 400

    def test_no_wages_when_not_actively_played(self) -> None:
        from world.currency.services import run_weekly_employment

        self._pool(200)
        assert run_weekly_employment(self.employment, was_active=False) == 0

    def test_partial_ap_partial_wages(self) -> None:
        from world.currency.services import run_weekly_employment

        self._pool(15)  # adventured most of it away
        assert run_weekly_employment(self.employment, was_active=True) == 150

    def test_chore_without_check_type_pays_base(self) -> None:
        from world.currency.services import work_chore

        self._pool(50)
        paid = work_chore(self.employment, ap_spent=10)
        assert paid == 100  # 10 AP × 10c × 1.0

    def test_chore_insufficient_ap_rejected(self) -> None:
        from django.core.exceptions import ValidationError as DjangoValidationError

        from world.currency.services import work_chore

        self._pool(5)
        with self.assertRaises(DjangoValidationError):
            work_chore(self.employment, ap_spent=10)

    def test_one_active_employment_constraint(self) -> None:
        from django.db import IntegrityError, transaction as db_transaction

        from world.currency.models import CharacterEmployment, Profession

        other = Profession.objects.create(name="Scribe", wage_per_ap=20)
        with db_transaction.atomic(), self.assertRaises(IntegrityError):
            CharacterEmployment.objects.create(character_sheet=self.sheet, profession=other)


class BusinessTests(TestCase):
    """Business variance and investment (#929)."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.currency.models import Business

        cls.persona = PersonaFactory()
        cls.business = Business.objects.create(owner_persona=cls.persona, name="The Gilded Anchor")

    def _fund(self, amount):
        from world.currency.services import get_or_create_purse, transfer

        purse = get_or_create_purse(self.persona.character_sheet)
        transfer(amount=amount, reason="seed", to_purse=purse)
        return purse

    def test_good_week_pays_profit(self) -> None:
        from world.currency.services import run_business_week

        net = run_business_week(self.business, fortune=50)
        assert net == 100  # level 1 × 200 base × 50%

    def test_bad_week_takes_real_money(self) -> None:
        from world.currency.services import run_business_week

        purse = self._fund(1_000)
        net = run_business_week(self.business, fortune=-50)
        assert net == -100
        purse.refresh_from_db()
        assert purse.balance == 900

    def test_loss_capped_at_purse(self) -> None:
        from world.currency.services import run_business_week

        purse = self._fund(30)
        net = run_business_week(self.business, fortune=-100)
        assert net == -30  # can't lose money you don't have
        purse.refresh_from_db()
        assert purse.balance == 0

    def test_investment_raises_level_and_yield(self) -> None:
        from world.currency.services import invest_in_business, run_business_week

        self._fund(120_000)
        invest_in_business(self.business, amount=100_000)
        self.business.refresh_from_db()
        assert self.business.level == 3  # 1 + 100k // 50k

        net = run_business_week(self.business, fortune=100)
        assert net == 600  # level 3 × 200 × 100%
