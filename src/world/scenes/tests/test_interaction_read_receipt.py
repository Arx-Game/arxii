from django.db import IntegrityError
from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.scenes.factories import InteractionFactory
from world.scenes.models import InteractionReadReceipt


class InteractionReadReceiptModelTests(TestCase):
    def test_creates_receipt_for_account_and_interaction(self) -> None:
        account = AccountFactory()
        interaction = InteractionFactory()
        receipt = InteractionReadReceipt.objects.create(
            interaction=interaction,
            timestamp=interaction.timestamp,
            account=account,
        )
        self.assertIsNotNone(receipt.seen_at)

    def test_unique_per_account_interaction_timestamp(self) -> None:
        account = AccountFactory()
        interaction = InteractionFactory()
        InteractionReadReceipt.objects.create(
            interaction=interaction,
            timestamp=interaction.timestamp,
            account=account,
        )
        with self.assertRaises(IntegrityError):
            InteractionReadReceipt.objects.create(
                interaction=interaction,
                timestamp=interaction.timestamp,
                account=account,
            )
