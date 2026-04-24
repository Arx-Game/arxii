from django.db import IntegrityError
from django.test import TestCase, TransactionTestCase

from world.narrative.constants import NarrativeCategory
from world.narrative.factories import (
    NarrativeMessageDeliveryFactory,
    NarrativeMessageFactory,
)


class NarrativeMessageTests(TestCase):
    def test_factory_creates_message(self) -> None:
        msg = NarrativeMessageFactory()
        self.assertIsNotNone(msg.body)
        self.assertEqual(msg.category, NarrativeCategory.STORY)
        self.assertIsNone(msg.sender_account)

    def test_category_choices(self) -> None:
        for category in NarrativeCategory.values:
            msg = NarrativeMessageFactory(category=category)
            self.assertEqual(msg.category, category)

    def test_ooc_note_is_blank_by_default(self) -> None:
        msg = NarrativeMessageFactory()
        self.assertEqual(msg.ooc_note, "")


class NarrativeMessageDeliveryTests(TestCase):
    def test_delivery_starts_unread_and_undelivered(self) -> None:
        delivery = NarrativeMessageDeliveryFactory()
        self.assertIsNone(delivery.delivered_at)
        self.assertIsNone(delivery.acknowledged_at)

    def test_message_can_fan_out_to_multiple_recipients(self) -> None:
        msg = NarrativeMessageFactory()
        d1 = NarrativeMessageDeliveryFactory(message=msg)
        d2 = NarrativeMessageDeliveryFactory(message=msg)
        self.assertEqual(msg.deliveries.count(), 2)
        self.assertNotEqual(d1.recipient_character_sheet, d2.recipient_character_sheet)


class NarrativeMessageDeliveryUniqueTests(TransactionTestCase):
    def test_unique_per_message_per_recipient(self) -> None:
        msg = NarrativeMessageFactory()
        d1 = NarrativeMessageDeliveryFactory(message=msg)
        with self.assertRaises(IntegrityError):
            NarrativeMessageDeliveryFactory(
                message=msg,
                recipient_character_sheet=d1.recipient_character_sheet,
            )
