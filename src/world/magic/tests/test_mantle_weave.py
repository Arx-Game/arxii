"""Tests for the MANTLE weave gate + anchor cap (#512 Mantle system, Task 4).

Weaving a MANTLE-kind Thread is gated on the character having cleared at least
level 1 of the mantle (codex research, recorded via the items.services.mantle
clearance recorder). The anchor cap for a MANTLE thread is
``max_cleared_level * 10`` (design §6.2), mirroring COVENANT_ROLE's
``covenant.level * 10``.
"""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.items.factories import MantleFactory, MantleLevelDefinitionFactory
from world.items.services.mantle import grant_mantle_clearance
from world.magic.constants import TargetKind
from world.magic.exceptions import MantleNotClearedError
from world.magic.factories import ResonanceFactory
from world.magic.models import Thread
from world.magic.services import compute_anchor_cap, weave_thread


class MantleWeaveGateTests(TestCase):
    """Weaving a MANTLE thread requires at least level-1 clearance."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.mantle = MantleFactory()
        cls.resonance = ResonanceFactory()

    def test_weave_without_clearance_raises(self) -> None:
        pre_count = Thread.objects.filter(owner=self.sheet).count()
        with self.assertRaises(MantleNotClearedError):
            weave_thread(self.sheet, TargetKind.MANTLE, self.mantle, self.resonance)
        self.assertEqual(Thread.objects.filter(owner=self.sheet).count(), pre_count)

    def test_weave_with_clearance_succeeds(self) -> None:
        grant_mantle_clearance(self.sheet, self.mantle, 1)
        self.sheet.character.mantle_clearances.invalidate()

        thread = weave_thread(
            self.sheet,
            TargetKind.MANTLE,
            self.mantle,
            self.resonance,
            name="Banner",
        )

        self.assertEqual(thread.target_kind, TargetKind.MANTLE)
        self.assertEqual(thread.target_mantle, self.mantle)
        self.assertEqual(thread.owner, self.sheet)
        self.assertEqual(thread.resonance, self.resonance)


class MantleAnchorCapTests(TestCase):
    """anchor cap == max_cleared_level * 10."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.mantle = MantleFactory()
        cls.resonance = ResonanceFactory()
        # Two authored levels so clearances at 1 and 2 are meaningful.
        MantleLevelDefinitionFactory(mantle=cls.mantle, level=1)
        MantleLevelDefinitionFactory(mantle=cls.mantle, level=2)

    def _weave(self) -> Thread:
        self.sheet.character.mantle_clearances.invalidate()
        return weave_thread(self.sheet, TargetKind.MANTLE, self.mantle, self.resonance)

    def test_cap_with_level_one_only(self) -> None:
        grant_mantle_clearance(self.sheet, self.mantle, 1)
        thread = self._weave()
        self.assertEqual(compute_anchor_cap(thread), 10)

    def test_cap_with_levels_one_and_two(self) -> None:
        grant_mantle_clearance(self.sheet, self.mantle, 1)
        grant_mantle_clearance(self.sheet, self.mantle, 2)
        thread = self._weave()
        self.assertEqual(compute_anchor_cap(thread), 20)
