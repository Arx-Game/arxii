"""``MakeoverConsentRequest``: one open ask per stylist/target pair (#4187)."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.items.factories import ItemInstanceFactory
from world.items.models import MakeoverConsentRequest
from world.scenes.action_constants import ActionRequestStatus
from world.scenes.factories import PersonaFactory


class MakeoverConsentRequestConstraintTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.stylist = PersonaFactory()
        cls.target = PersonaFactory()
        cls.item = ItemInstanceFactory()

    def ask(self, **overrides):
        values = {
            "stylist_persona": self.stylist,
            "target_persona": self.target,
            "item_instance": self.item,
        }
        values.update(overrides)
        return MakeoverConsentRequest.objects.create(**values)

    def test_two_pending_asks_for_one_pair_are_refused(self):
        self.ask()
        with transaction.atomic(), self.assertRaises(IntegrityError):
            self.ask()

    def test_a_resolved_ask_does_not_block_a_new_one(self):
        self.ask(status=ActionRequestStatus.DENIED)
        second = self.ask()
        self.assertEqual(second.status, ActionRequestStatus.PENDING)
        self.assertEqual(second.descriptor, "")
        self.assertFalse(second.blend)
        self.assertIsNone(second.option)
