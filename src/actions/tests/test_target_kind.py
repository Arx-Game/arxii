from django.test import TestCase

from actions.constants import TargetKind


class TargetKindTests(TestCase):
    def test_enum_members(self) -> None:
        self.assertEqual(TargetKind.PERSONA.value, "persona")
        self.assertEqual(TargetKind.CHARACTER.value, "character")
        self.assertEqual(TargetKind.ITEM.value, "item")
        self.assertEqual(TargetKind.ROOM.value, "room")
