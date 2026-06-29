"""Tests for the GIFT branch of compute_anchor_cap (#1580).

GIFT thread anchor cap = current_path_stage(owner) × ANCHOR_CAP_GIFT_PER_STAGE (10).
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import ANCHOR_CAP_GIFT_PER_STAGE
from world.magic.factories import GiftFactory, ResonanceFactory
from world.magic.models import Thread
from world.magic.services import compute_anchor_cap
from world.magic.specialization.services import provision_latent_gift_thread


class GiftAnchorCapTests(TestCase):
    """compute_anchor_cap for GIFT-kind threads: path_stage × ANCHOR_CAP_GIFT_PER_STAGE."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.gift = GiftFactory()
        cls.resonance = ResonanceFactory()
        cls.gift.resonances.add(cls.resonance)

    def _gift_thread(self, path_stage: int) -> Thread:
        """Return a level-0 GIFT thread whose owner has the given path stage."""
        sheet = CharacterSheetFactory(_path_stage=path_stage)
        provision_latent_gift_thread(sheet, self.gift, resonance=self.resonance)
        return Thread.objects.get(
            owner=sheet,
            target_kind="GIFT",
            target_gift=self.gift,
        )

    def test_gift_anchor_cap_stage_two(self) -> None:
        """Owner at path stage 2 → anchor cap = 2 × 10 = 20."""
        thread = self._gift_thread(path_stage=2)
        self.assertEqual(compute_anchor_cap(thread), 20)

    def test_gift_anchor_cap_stage_zero(self) -> None:
        """Owner at path stage 0 → anchor cap = 0 × 10 = 0."""
        thread = self._gift_thread(path_stage=0)
        self.assertEqual(compute_anchor_cap(thread), 0)

    def test_gift_per_stage_constant_is_ten(self) -> None:
        """Tuning constant is 10; changing it here would invalidate the formula tests."""
        self.assertEqual(ANCHOR_CAP_GIFT_PER_STAGE, 10)
