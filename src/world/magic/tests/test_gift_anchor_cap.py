"""Tests for the GIFT branch of compute_anchor_cap (#1580, #4585).

A gift has no cap value of its own, so a GIFT thread's anchor cap is the owner's
level cap: ``compute_level_cap(owner)`` = character level × 10. Path stage no longer
enters any thread cap (#4585).
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import GiftFactory, ResonanceFactory
from world.magic.models import Thread
from world.magic.services import compute_anchor_cap
from world.magic.specialization.services import provision_latent_gift_thread


class GiftAnchorCapTests(TestCase):
    """compute_anchor_cap for GIFT-kind threads: the owner's level cap."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.gift = GiftFactory()
        cls.resonance = ResonanceFactory()
        cls.gift.resonances.add(cls.resonance)

    def _gift_thread(self, **sheet_kwargs: object) -> Thread:
        """Return a level-0 GIFT thread on a sheet built with ``sheet_kwargs``."""
        sheet = CharacterSheetFactory(**sheet_kwargs)
        provision_latent_gift_thread(sheet, self.gift, resonance=self.resonance)
        return Thread.objects.get(
            owner=sheet,
            target_kind="GIFT",
            target_gift=self.gift,
        )

    def test_gift_anchor_cap_follows_character_level(self) -> None:
        """A level-4 owner → anchor cap = 4 × 10 = 40."""
        thread = self._gift_thread(_class_level=4)
        self.assertEqual(compute_anchor_cap(thread), 40)

    def test_gift_anchor_cap_without_class_level_is_ten(self) -> None:
        """No class level → get_character_path_level returns 1 → cap 10, never 0."""
        thread = self._gift_thread()
        self.assertEqual(compute_anchor_cap(thread), 10)

    def test_gift_anchor_cap_ignores_path_stage(self) -> None:
        """A high Path stage no longer raises the cap; only character level does."""
        thread = self._gift_thread(_path_stage=5, _class_level=2)
        self.assertEqual(compute_anchor_cap(thread), 20)
