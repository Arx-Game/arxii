"""TargetKind.GIFT exists for gift-anchored threads (#1578)."""

from django.test import SimpleTestCase

from world.magic.constants import TargetKind


class TargetKindGiftTests(SimpleTestCase):
    def test_gift_target_kind_exists(self) -> None:
        assert TargetKind.GIFT.value == "GIFT"
        assert (TargetKind.GIFT, "Gift") in TargetKind.choices
