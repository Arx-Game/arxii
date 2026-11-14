"""The perks a pulled thread gives are the paying resonance's perks (#5123)."""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterResonanceFactory,
    ResonanceFactory,
    ThreadFactory,
    ThreadPullCostFactory,
    ThreadPullEffectFactory,
    ThreadResonanceFactory,
)
from world.magic.services import preview_resonance_pull, resolve_pull_effects
from world.magic.services.thread_rows import payer_level_read


class PayerPerkTests(TestCase):
    def setUp(self) -> None:
        # Built per test: the thread handler caches a thread's resonance rows on the
        # (idmapper-shared) character, so a class-level thread would serve one test's rows
        # to the next.
        self.sheet = CharacterSheetFactory()
        self.fury = ResonanceFactory(name="Fury")
        self.guile = ResonanceFactory(name="Guile")
        self.unheld = ResonanceFactory(name="Unimbued")

    def _thread(self, level: int):
        thread = ThreadFactory(owner=self.sheet, resonance=self.fury, level=level)
        ThreadResonanceFactory(thread=thread, resonance=self.guile, amount=0)
        return thread

    def _perk(self, resonance, *, tier: int = 1, amount: int = 1, min_level: int = 0) -> None:
        ThreadPullEffectFactory(
            resonance=resonance, tier=tier, flat_bonus_amount=amount, min_thread_level=min_level
        )

    def test_leading_payer_gets_its_perks_at_full_level(self) -> None:
        thread = self._thread(30)
        self._perk(self.fury, tier=1, amount=2)

        effects = resolve_pull_effects([thread], 1, in_combat=False)

        self.assertEqual(payer_level_read(thread, self.fury), 30)
        self.assertEqual([e.scaled_value for e in effects], [6])
        self.assertEqual(effects[0].level_multiplier, 3)

    def test_second_payer_gets_its_own_perks_one_step_lower(self) -> None:
        thread = self._thread(30)
        self._perk(self.fury, tier=1, amount=2)
        self._perk(self.guile, tier=1, amount=5)
        self._perk(self.guile, tier=1, amount=9, min_level=30)

        effects = resolve_pull_effects([thread], 1, in_combat=False, payers={thread.pk: self.guile})

        self.assertEqual(payer_level_read(thread, self.guile), 20)
        # Guile's own row at level 20 (multiplier 2); the row gated at 30 is out of reach.
        self.assertEqual([e.scaled_value for e in effects], [10])
        self.assertEqual(effects[0].source_thread_level, 30)

    def test_second_payer_never_outmultiplies_leader_below_10(self) -> None:
        thread = self._thread(5)
        self._perk(self.fury, tier=1, amount=10)
        self._perk(self.guile, tier=1, amount=10)

        leader = resolve_pull_effects([thread], 1, in_combat=False)
        second = resolve_pull_effects([thread], 1, in_combat=False, payers={thread.pk: self.guile})

        # Level 0 would read multiplier 1 against the leader's 0.5; it reads level 5 instead.
        self.assertEqual(payer_level_read(thread, self.guile), 5)
        self.assertLessEqual(second[0].scaled_value, leader[0].scaled_value)

    def test_unimbued_payer_gets_no_perks(self) -> None:
        thread = self._thread(30)
        self._perk(self.unheld, tier=1, amount=4)

        effects = resolve_pull_effects(
            [thread], 1, in_combat=False, payers={thread.pk: self.unheld}
        )

        self.assertIsNone(payer_level_read(thread, self.unheld))
        self.assertEqual(effects, [])

    def test_tier_zero_only_for_leading_payer(self) -> None:
        thread = self._thread(30)
        for resonance in (self.fury, self.guile):
            self._perk(resonance, tier=0, amount=1)
            self._perk(resonance, tier=1, amount=1)

        leading = resolve_pull_effects([thread], 1, in_combat=False)
        second = resolve_pull_effects([thread], 1, in_combat=False, payers={thread.pk: self.guile})

        self.assertEqual(sorted(e.source_tier for e in leading), [0, 1])
        self.assertEqual([e.source_tier for e in second], [1])

    def test_preview_lists_effects_per_payer(self) -> None:
        thread = self._thread(30)
        CharacterAnimaFactory(character=self.sheet, current=20, maximum=20)
        ThreadPullCostFactory(tier=1, resonance_cost=2, anima_per_thread=1)
        for resonance in (self.fury, self.guile, self.unheld):
            CharacterResonanceFactory(
                character_sheet=self.sheet, resonance=resonance, balance=10, lifetime_earned=10
            )
        self._perk(self.fury, tier=1, amount=2)
        self._perk(self.guile, tier=1, amount=5)

        preview = preview_resonance_pull(self.sheet, 1, [thread])

        options = {o.resonance.pk: o for o in preview.per_thread[0].options}
        self.assertEqual([e.scaled_value for e in options[self.fury.pk].effects], [6])
        self.assertEqual(options[self.fury.pk].level_read, 30)
        self.assertEqual([e.scaled_value for e in options[self.guile.pk].effects], [10])
        self.assertEqual(options[self.guile.pk].level_read, 20)
        self.assertEqual(options[self.unheld.pk].effects, [])
