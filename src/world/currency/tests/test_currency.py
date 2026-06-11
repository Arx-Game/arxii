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
