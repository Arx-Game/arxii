"""Model-layer tests: constraints, clean() coherence, config singleton (#1985)."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from world.estates.constants import BequestKind
from world.estates.factories import (
    BequestFactory,
    EstateSettlementFactory,
    WillExecutorFactory,
    WillFactory,
)
from world.estates.models import EstateConfig, get_estate_config
from world.items.factories import ItemInstanceFactory
from world.scenes.factories import PersonaFactory
from world.societies.factories import OrganizationFactory


class BequestValidationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.will = WillFactory()
        cls.persona = PersonaFactory()
        cls.org = OrganizationFactory()
        cls.item = ItemInstanceFactory()

    def test_recipient_xor_constraint_rejects_both(self):
        with transaction.atomic(), self.assertRaises(IntegrityError):
            BequestFactory(
                will=self.will,
                kind=BequestKind.ALL_COIN,
                recipient_persona=self.persona,
                recipient_organization=self.org,
            )

    def test_recipient_xor_constraint_rejects_neither(self):
        with transaction.atomic(), self.assertRaises(IntegrityError):
            BequestFactory(will=self.will, kind=BequestKind.ALL_COIN, recipient_persona=None)

    def test_one_residuary_per_will(self):
        BequestFactory(will=self.will, kind=BequestKind.RESIDUARY)
        with transaction.atomic(), self.assertRaises(IntegrityError):
            BequestFactory(will=self.will, kind=BequestKind.RESIDUARY)

    def test_specific_item_requires_item(self):
        bequest = BequestFactory.build(
            will=self.will, kind=BequestKind.SPECIFIC_ITEM, recipient_persona=self.persona
        )
        with self.assertRaises(ValidationError):
            bequest.clean()

    def test_specific_item_with_item_is_clean(self):
        bequest = BequestFactory.build(
            will=self.will,
            kind=BequestKind.SPECIFIC_ITEM,
            item=self.item,
            recipient_persona=self.persona,
        )
        bequest.clean()

    def test_coin_amount_requires_positive_amount(self):
        bequest = BequestFactory.build(
            will=self.will, kind=BequestKind.COIN_AMOUNT, recipient_persona=self.persona
        )
        with self.assertRaises(ValidationError):
            bequest.clean()

    def test_residuary_may_not_carry_targets(self):
        bequest = BequestFactory.build(
            will=self.will,
            kind=BequestKind.RESIDUARY,
            item=self.item,
            recipient_persona=self.persona,
        )
        with self.assertRaises(ValidationError):
            bequest.clean()

    def test_all_coin_may_not_carry_amount(self):
        bequest = BequestFactory.build(
            will=self.will,
            kind=BequestKind.ALL_COIN,
            amount=100,
            recipient_persona=self.persona,
        )
        with self.assertRaises(ValidationError):
            bequest.clean()

    def test_org_recipient_is_valid(self):
        bequest = BequestFactory(
            will=self.will,
            kind=BequestKind.ALL_COIN,
            recipient_persona=None,
            recipient_organization=self.org,
        )
        self.assertEqual(bequest.recipient_organization, self.org)


class WillExecutorTests(TestCase):
    def test_duplicate_executor_rejected(self):
        executor = WillExecutorFactory()
        with transaction.atomic(), self.assertRaises(IntegrityError):
            WillExecutorFactory(will=executor.will, persona=executor.persona)


class EstateSettlementTests(TestCase):
    def test_one_settlement_per_sheet(self):
        settlement = EstateSettlementFactory()
        with transaction.atomic(), self.assertRaises(IntegrityError):
            EstateSettlementFactory(character_sheet=settlement.character_sheet)


class EstateConfigTests(TestCase):
    def test_get_estate_config_creates_singleton(self):
        self.assertEqual(EstateConfig.objects.count(), 0)
        config = get_estate_config()
        self.assertEqual(config.settlement_window_days, 14)
        self.assertEqual(get_estate_config().pk, config.pk)
        self.assertEqual(EstateConfig.objects.count(), 1)
