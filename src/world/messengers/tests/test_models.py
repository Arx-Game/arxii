"""Database guards on missive attachments (#3289)."""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.conditions.factories import CapabilityTypeFactory
from world.items.factories import ItemInstanceFactory
from world.messengers.constants import AttachmentResolution
from world.messengers.factories import (
    MissiveAttachmentFactory,
    MissiveFactory,
    TransmissionMethodFactory,
)


class MissiveAttachmentConstraintTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.missive = MissiveFactory()
        cls.other_missive = MissiveFactory()
        cls.item = ItemInstanceFactory()

    def test_attachment_cannot_carry_both_item_and_coin(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            MissiveAttachmentFactory(missive=self.missive, item=self.item, coin_amount=5)

    def test_coin_attachment_needs_a_positive_amount(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            MissiveAttachmentFactory(missive=self.missive, item=None, coin_amount=0)

    def test_item_cannot_ride_two_missives_at_once(self) -> None:
        MissiveAttachmentFactory(missive=self.missive, item=self.item, coin_amount=None)
        with self.assertRaises(IntegrityError), transaction.atomic():
            MissiveAttachmentFactory(missive=self.other_missive, item=self.item, coin_amount=None)

    def test_resolved_item_can_ride_again(self) -> None:
        MissiveAttachmentFactory(
            missive=self.missive,
            item=self.item,
            coin_amount=None,
            resolution=AttachmentResolution.REFUSED,
        )
        attachment = MissiveAttachmentFactory(
            missive=self.other_missive, item=self.item, coin_amount=None
        )
        self.assertEqual(attachment.resolution, AttachmentResolution.PENDING)


class TransmissionMethodConstraintTests(TestCase):
    def test_universal_method_cannot_require_a_capability(self) -> None:
        capability = CapabilityTypeFactory()
        with self.assertRaises(IntegrityError), transaction.atomic():
            TransmissionMethodFactory(is_universal=True, required_capability=capability)
