"""ThreadPullEffect.target_gift — gift-specific lookup + partial-constraint tests.

Verifies:
  1. Gift-specific row is preferred over null-fallback when both exist for a GIFT thread.
  2. A GIFT thread with no gift-specific row falls back to the null-target_gift row.
  3. COVENANT_ROLE pulls still resolve null-target_gift rows (non-regression).
  4. Partial UniqueConstraint behaviour:
     - Two null-target_gift rows with the same base key raise IntegrityError.
     - A null-target_gift row + a gift-specific row with the same base key coexist.

Uses FactoryBoy + setUpTestData.  GIFT threads are minted via
``provision_latent_gift_thread`` (the canonical CG provisioning path).
"""

from typing import ClassVar

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import CharacterSheet
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
)
from world.magic.constants import EffectKind, TargetKind
from world.magic.factories import (
    GiftFactory,
    ResonanceFactory,
    ThreadPullEffectFactory,
)
from world.magic.models import Gift, Resonance, Thread, ThreadPullEffect
from world.magic.services.pull_effects import get_pull_effects_for_thread
from world.magic.specialization.services import provision_latent_gift_thread


class GiftSpecificLookupTests(TestCase):
    """get_pull_effects_for_thread resolves gift-specific rows correctly."""

    sheet: ClassVar[CharacterSheet]
    gift: ClassVar[Gift]
    resonance: ClassVar[Resonance]
    thread: ClassVar[Thread]
    null_row: ClassVar[ThreadPullEffect]
    gift_row: ClassVar[ThreadPullEffect]

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.gift = GiftFactory()
        cls.resonance = ResonanceFactory()
        cls.gift.resonances.add(cls.resonance)

        # Mint the latent GIFT thread (the canonical CG provisioning path).
        cls.thread = provision_latent_gift_thread(cls.sheet, cls.gift, resonance=cls.resonance)

        # Null-fallback row (universal, target_gift=NULL).
        cls.null_row = ThreadPullEffectFactory(
            target_kind=TargetKind.GIFT,
            resonance=cls.resonance,
            tier=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=5,
            target_gift=None,
        )
        # Gift-specific row for the same base key.
        cls.gift_row = ThreadPullEffectFactory(
            target_kind=TargetKind.GIFT,
            resonance=cls.resonance,
            tier=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=20,
            target_gift=cls.gift,
        )

    def test_gift_specific_row_resolves(self) -> None:
        """Lookup for a GIFT thread returns the gift-specific row, not the fallback."""
        rows = get_pull_effects_for_thread(
            self.thread,
            tier=0,
            effect_kind=EffectKind.FLAT_BONUS,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].pk, self.gift_row.pk)
        self.assertEqual(rows[0].flat_bonus_amount, 20)

    def test_different_gift_falls_back_to_null(self) -> None:
        """A GIFT thread for a different gift (no specific row) falls back to null."""
        other_gift = GiftFactory()
        other_gift.resonances.add(self.resonance)
        other_thread = provision_latent_gift_thread(
            self.sheet, other_gift, resonance=self.resonance
        )
        rows = get_pull_effects_for_thread(
            other_thread,
            tier=0,
            effect_kind=EffectKind.FLAT_BONUS,
        )
        # No gift-specific row for other_gift → falls back to null_row (amount=5).
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].pk, self.null_row.pk)
        self.assertEqual(rows[0].flat_bonus_amount, 5)

    def test_no_rows_at_all_returns_empty(self) -> None:
        """A GIFT thread with no authored effects returns an empty list."""
        empty_gift = GiftFactory()
        empty_resonance = ResonanceFactory()
        empty_gift.resonances.add(empty_resonance)
        empty_thread = provision_latent_gift_thread(
            self.sheet, empty_gift, resonance=empty_resonance
        )
        rows = get_pull_effects_for_thread(
            empty_thread,
            tier=0,
            effect_kind=EffectKind.FLAT_BONUS,
        )
        self.assertEqual(rows, [])


class GiftFallbackOnlyTests(TestCase):
    """GIFT thread with only a null-fallback row uses it correctly."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.gift = GiftFactory()
        cls.resonance = ResonanceFactory()
        cls.gift.resonances.add(cls.resonance)
        cls.thread = provision_latent_gift_thread(cls.sheet, cls.gift, resonance=cls.resonance)
        # Only the null-fallback row — no gift-specific row.
        cls.null_row = ThreadPullEffectFactory(
            target_kind=TargetKind.GIFT,
            resonance=cls.resonance,
            tier=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=7,
            target_gift=None,
        )

    def test_null_target_gift_used_as_fallback(self) -> None:
        """When no gift-specific row exists the null-fallback row is returned."""
        rows = get_pull_effects_for_thread(
            self.thread,
            tier=0,
            effect_kind=EffectKind.FLAT_BONUS,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].pk, self.null_row.pk)
        self.assertEqual(rows[0].flat_bonus_amount, 7)


class CovenantRoleNonRegressionTests(TestCase):
    """COVENANT_ROLE pull resolution is byte-identical to pre-#1580 behaviour."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()

        covenant = CovenantFactory()
        cls.role = CovenantRoleFactory(covenant_type=covenant.covenant_type)
        CharacterCovenantRoleFactory(
            character_sheet=cls.sheet,
            covenant=covenant,
            covenant_role=cls.role,
            engaged=True,
        )

        # Null-target_gift COVENANT_ROLE pull effect.
        cls.covenant_row = ThreadPullEffectFactory(
            target_kind=TargetKind.COVENANT_ROLE,
            resonance=cls.resonance,
            tier=1,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=3,
            target_gift=None,
        )

        # Weave a COVENANT_ROLE thread.
        cls.thread = Thread.objects.create(
            owner=cls.sheet,
            resonance=cls.resonance,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=cls.role,
            level=10,
        )

    def test_covenant_null_row_resolves(self) -> None:
        """COVENANT_ROLE resolver returns the null-target_gift row (non-regression)."""
        rows = get_pull_effects_for_thread(
            self.thread,
            tier=1,
            effect_kind=EffectKind.FLAT_BONUS,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].pk, self.covenant_row.pk)

    def test_covenant_ignores_gift_specific_rows(self) -> None:
        """A gift-specific ThreadPullEffect row is never returned for COVENANT_ROLE threads."""
        gift = GiftFactory()
        # Seed a gift-specific row that happens to share the same (resonance, tier).
        gift_row = ThreadPullEffectFactory(
            target_kind=TargetKind.GIFT,
            resonance=self.resonance,
            tier=1,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=99,
            target_gift=gift,
        )
        rows = get_pull_effects_for_thread(
            self.thread,
            tier=1,
            effect_kind=EffectKind.FLAT_BONUS,
        )
        pks = {r.pk for r in rows}
        self.assertNotIn(gift_row.pk, pks)
        self.assertIn(self.covenant_row.pk, pks)


class PartialUniqueConstraintTests(TestCase):
    """Two-partial-constraint guarantees — the non-regression invariant.

    (a) Two null-target_gift rows with the same base key → IntegrityError.
    (b) A null-target_gift row + a gift-specific row with the same base key coexist.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.resonance = ResonanceFactory()
        cls.gift = GiftFactory()

    def test_duplicate_null_rows_raise_integrity_error(self) -> None:
        """Covenant guarantee: two null-target_gift rows with the same key are rejected."""
        ThreadPullEffectFactory(
            target_kind=TargetKind.COVENANT_ROLE,
            resonance=self.resonance,
            tier=0,
            min_thread_level=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=1,
            target_gift=None,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ThreadPullEffectFactory(
                    target_kind=TargetKind.COVENANT_ROLE,
                    resonance=self.resonance,
                    tier=0,
                    min_thread_level=0,
                    effect_kind=EffectKind.FLAT_BONUS,
                    flat_bonus_amount=2,
                    target_gift=None,
                )

    def test_null_row_and_gift_row_coexist(self) -> None:
        """A null-target_gift row and a gift-specific row with the same base key coexist."""
        null_row = ThreadPullEffectFactory(
            target_kind=TargetKind.GIFT,
            resonance=self.resonance,
            tier=0,
            min_thread_level=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=5,
            target_gift=None,
        )
        gift_row = ThreadPullEffectFactory(
            target_kind=TargetKind.GIFT,
            resonance=self.resonance,
            tier=0,
            min_thread_level=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=10,
            target_gift=self.gift,
        )
        # Both rows must be persisted without IntegrityError.
        self.assertIsNotNone(null_row.pk)
        self.assertIsNotNone(gift_row.pk)
        self.assertNotEqual(null_row.pk, gift_row.pk)
