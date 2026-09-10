from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.scenes.factories import InteractionFactory
from world.scenes.models import InteractionReadReceipt
from world.scenes.read_state_services import mark_poses_read


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


class MarkPosesReadServiceTests(TestCase):
    def test_marks_poses_read_and_is_idempotent(self) -> None:
        account = AccountFactory()
        interaction = InteractionFactory()
        pair = (interaction.pk, interaction.timestamp.isoformat())

        created_first = mark_poses_read(account=account, poses=[pair])
        created_second = mark_poses_read(account=account, poses=[pair])

        self.assertEqual(created_first, 1)
        self.assertEqual(created_second, 0)
        self.assertEqual(
            InteractionReadReceipt.objects.filter(account=account, interaction=interaction).count(),
            1,
        )


class IsUnreadSerializerFieldTests(APITestCase):
    def test_marked_read_pose_is_not_unread(self) -> None:
        account = AccountFactory()
        interaction = InteractionFactory()
        self.client.force_authenticate(user=account)

        before = self.client.get(reverse("interaction-list")).json()
        row_before = next(r for r in before["results"] if r["id"] == interaction.pk)
        self.assertTrue(row_before["is_unread"])

        mark_poses_read(
            account=account, poses=[(interaction.pk, interaction.timestamp.isoformat())]
        )

        after = self.client.get(reverse("interaction-list")).json()
        row_after = next(r for r in after["results"] if r["id"] == interaction.pk)
        self.assertFalse(row_after["is_unread"])
