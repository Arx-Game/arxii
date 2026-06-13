from django.test import SimpleTestCase

from actions.constants import ActionBackend, CombatActionSlot
from actions.types import ActionRef


class ActionRefSlotTest(SimpleTestCase):
    def test_focused_slot_default_none(self):
        ref = ActionRef(backend=ActionBackend.COMBAT, technique_id=7)
        self.assertIsNone(ref.action_slot)

    def test_passive_slot_requires_technique(self):
        with self.assertRaises(ValueError):
            ActionRef(
                backend=ActionBackend.COMBAT,
                technique_id=None,
                action_slot=CombatActionSlot.PASSIVE_PHYSICAL,
            )

    def test_passive_slot_with_technique_ok(self):
        ref = ActionRef(
            backend=ActionBackend.COMBAT,
            technique_id=7,
            action_slot=CombatActionSlot.PASSIVE_SOCIAL,
        )
        self.assertEqual(ref.action_slot, CombatActionSlot.PASSIVE_SOCIAL)
