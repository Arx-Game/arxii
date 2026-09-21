from datetime import timedelta
from unittest.mock import patch

from django.db import IntegrityError, connection, transaction
from django.test import TestCase, tag
from django.urls import reverse
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.scenes.factories import InteractionFactory
from world.scenes.models import InteractionReadReceipt
from world.scenes.read_state_services import mark_conversation_read, mark_poses_read


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


class MarkConversationReadCapOrderingTests(TestCase):
    """`mark_conversation_read`'s over-cap slice must keep the NEWEST poses.

    This is a direct unit test of the service function itself -- deliberately
    NOT going through the full HTTP/DB path with thousands of real rows.
    The test uses three real interactions because PostgreSQL enforces the
    receipt's composite `(id, timestamp)` reference.

    The correctness of `poses[-N:]` depends entirely on the caller (in
    practice, `play_views._mark_conversation_read`) handing this function an
    ASCENDING (oldest-first) list, mirroring `_queryset`'s
    `.order_by("timestamp", "id")`. Nothing else in this module would catch a
    future regression of that ordering assumption -- this test pins it down
    directly, independent of the view/HTTP layer.
    """

    def test_over_cap_keeps_the_newest_poses_not_the_oldest(self) -> None:
        account = AccountFactory()
        # Ascending (oldest-first), matching `_queryset`'s `order_by`. Use
        # real rows because PostgreSQL now enforces the composite reference.
        interactions = [InteractionFactory() for _ in range(3)]
        ascending_poses = [
            (interaction.pk, interaction.timestamp.isoformat()) for interaction in interactions
        ]

        with patch("world.scenes.read_state_services.MAX_CONVERSATION_MARK_READ", 2):
            created = mark_conversation_read(account=account, poses=ascending_poses)

        self.assertEqual(created, 2)
        marked_ids = set(
            InteractionReadReceipt.objects.filter(account=account).values_list(
                "interaction_id", flat=True
            )
        )
        # The tail of the input list (the NEWEST two), never the head (oldest)
        # -- a `poses[:N]` regression would instead keep the first two.
        self.assertEqual(marked_ids, {interactions[1].pk, interactions[2].pk})


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


@tag("postgres")
class PartitionedMetadataIntegrityTests(TestCase):
    """PostgreSQL enforces the full ``(interaction_id, timestamp)`` reference."""

    def test_receipt_timestamp_must_match_partition_key(self) -> None:
        account = AccountFactory()
        interaction = InteractionFactory()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                InteractionReadReceipt.objects.create(
                    interaction_id=interaction.pk,
                    timestamp=interaction.timestamp + timedelta(seconds=1),
                    account=account,
                )
                # The production FK is intentionally deferred for delete
                # ordering. Force it now so this test can assert the mismatch.
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SET CONSTRAINTS interactionreadreceipt_interaction_fk IMMEDIATE"
                    )

    def test_deleting_interaction_cleans_receipt(self) -> None:
        account = AccountFactory()
        interaction = InteractionFactory()
        receipt = InteractionReadReceipt.objects.create(
            interaction=interaction, timestamp=interaction.timestamp, account=account
        )
        interaction.delete()
        self.assertFalse(InteractionReadReceipt.objects.filter(pk=receipt.pk).exists())
