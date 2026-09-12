from django.test import TestCase

from world.scenes.factories import InteractionFactory
from world.scenes.models import InteractionReply


class InteractionReplyModelTest(TestCase):
    """The parent-edge bridge stores one edge per reply, partition-safely."""

    @classmethod
    def setUpTestData(cls):
        cls.parent = InteractionFactory()
        cls.child = InteractionFactory()

    def test_stores_the_edge_with_both_timestamps(self):
        row = InteractionReply.objects.create(
            interaction=self.child,
            timestamp=self.child.timestamp,
            parent=self.parent,
            parent_timestamp=self.parent.timestamp,
        )
        self.assertEqual(row.parent_id, self.parent.pk)
        self.assertEqual(row.parent_timestamp, self.parent.timestamp)

    def test_a_reply_has_at_most_one_parent(self):
        InteractionReply.objects.create(
            interaction=self.child,
            timestamp=self.child.timestamp,
            parent=self.parent,
            parent_timestamp=self.parent.timestamp,
        )
        other = InteractionFactory()
        with self.assertRaises(Exception):  # noqa: B017 - IntegrityError, backend-dependent
            InteractionReply.objects.create(
                interaction=self.child,
                timestamp=self.child.timestamp,
                parent=other,
                parent_timestamp=other.timestamp,
            )

    def test_neither_fk_declares_a_database_constraint(self):
        # The partition trap: an ordinary FK to arxii_interaction's id cannot
        # exist, because the table's PK is composite.
        for name in ("interaction", "parent"):
            self.assertFalse(InteractionReply._meta.get_field(name).db_constraint)
