"""Regression tests: a distinction's resonance-scoped POWER modifier boosts both a cast
AND a standalone thread-pull keyed to the same resonance (#1834 Task 7 — potency axis).

A distinction expresses potency for a resonance by authoring a ``DistinctionEffect`` whose
``target`` is a POWER-category ``ModifierTarget`` gated by ``target_resonance``. That's the
same seam ``motif_coherence_bonus`` and tier-0 thread-pull FLAT_BONUS rows ride. This module
proves the resulting ``CharacterModifier`` lands on:

- a technique cast keyed to that resonance (``_derive_power``'s FLAT stage) — already wired,
  kept here as a regression guard.
- a standalone thread-pull on an R-thread (``spend_resonance_for_pull`` /
  ``preview_resonance_pull``) — the gap this task wires via
  ``world.mechanics.services.power_flat_bonus_for_resonance`` and
  ``world.magic.services.resonance._fold_distinction_pull_bonus``.

``DistinctionResonancePotencyUnscopedTests`` additionally proves cast/pull parity for an
UNSCOPED (``target_resonance=None``) POWER effect — it must boost a pull of any resonance,
exactly as it already boosts every cast (final-review Finding 2).
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.factories import (
    CharacterDistinctionFactory,
    DistinctionEffectFactory,
    DistinctionFactory,
)
from world.magic.constants import EffectKind
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterResonanceFactory,
    ResonanceFactory,
    TechniqueFactory,
    ThreadFactory,
    ThreadPullCostFactory,
)
from world.magic.services.resonance import preview_resonance_pull, spend_resonance_for_pull
from world.magic.services.techniques import _derive_power
from world.magic.types import PullActionContext
from world.mechanics.constants import POWER_CATEGORY_NAME
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.mechanics.services import create_distinction_modifiers


class DistinctionResonancePotencyTests(TestCase):
    """One distinction, one resonance-scoped POWER target, exercised on cast + pull."""

    def setUp(self) -> None:
        self.resonance = ResonanceFactory(name="Predatory")
        self.power_category = ModifierCategoryFactory(name=POWER_CATEGORY_NAME)
        self.power_target = ModifierTargetFactory(
            category=self.power_category,
            name="power_predatory",
            target_resonance=self.resonance,
        )

        self.distinction = DistinctionFactory(name="Predator's Instinct")
        DistinctionEffectFactory(
            distinction=self.distinction,
            target=self.power_target,
            value_per_rank=6,
        )
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        char_distinction = CharacterDistinctionFactory(
            character=self.sheet,
            distinction=self.distinction,
            rank=1,
        )
        create_distinction_modifiers(char_distinction)

    def test_cast_power_is_boosted_by_resonance_scoped_distinction(self) -> None:
        """Regression guard: cast power already reads this modifier (_derive_power FLAT stage)."""
        technique = TechniqueFactory()
        technique.gift.resonances.add(self.resonance)

        ledger = _derive_power(channeled_intensity=5, technique=technique, character=self.character)

        self.assertEqual(ledger.total, 5 + 6)

    def test_thread_pull_is_boosted_by_resonance_scoped_distinction(self) -> None:
        """The gap: a standalone thread-pull on an R-thread must also carry the bonus."""
        CharacterAnimaFactory(character=self.character, current=10, maximum=10)
        CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=self.resonance,
            balance=10,
            lifetime_earned=10,
        )
        ThreadPullCostFactory(tier=1, resonance_cost=2, anima_per_thread=1)
        thread = ThreadFactory(owner=self.sheet, resonance=self.resonance, level=1)
        ctx = PullActionContext(
            combat_encounter=None,
            participant=None,
            involved_traits=(thread.target_trait_id,),
        )

        result = spend_resonance_for_pull(
            self.sheet,
            self.resonance,
            tier=1,
            threads=[thread],
            action_context=ctx,
        )

        flat_bonus_total = sum(
            r.scaled_value or 0 for r in result.resolved_effects if r.kind == EffectKind.FLAT_BONUS
        )
        self.assertEqual(flat_bonus_total, 6)

    def test_thread_pull_preview_also_reflects_the_bonus(self) -> None:
        """preview_resonance_pull must match the eventual commit's magnitude — no state mutation."""
        ThreadPullCostFactory(tier=1, resonance_cost=2, anima_per_thread=1)
        thread = ThreadFactory(owner=self.sheet, resonance=self.resonance, level=1)

        preview = preview_resonance_pull(
            self.sheet,
            self.resonance,
            tier=1,
            threads=[thread],
        )

        flat_bonus_total = sum(
            r.scaled_value or 0 for r in preview.resolved_effects if r.kind == EffectKind.FLAT_BONUS
        )
        self.assertEqual(flat_bonus_total, 6)

    def test_thread_pull_on_a_different_resonance_is_not_boosted(self) -> None:
        """Gate check: the distinction bonus is resonance-scoped, not a blanket pull buff."""
        other_resonance = ResonanceFactory(name="Serene")
        CharacterAnimaFactory(character=self.character, current=10, maximum=10)
        CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=other_resonance,
            balance=10,
            lifetime_earned=10,
        )
        ThreadPullCostFactory(tier=1, resonance_cost=2, anima_per_thread=1)
        thread = ThreadFactory(owner=self.sheet, resonance=other_resonance, level=1)

        preview = preview_resonance_pull(
            self.sheet,
            other_resonance,
            tier=1,
            threads=[thread],
        )

        flat_bonus_total = sum(
            r.scaled_value or 0 for r in preview.resolved_effects if r.kind == EffectKind.FLAT_BONUS
        )
        self.assertEqual(flat_bonus_total, 0)


class DistinctionResonancePotencyUnscopedTests(TestCase):
    """An UNSCOPED (target_resonance=None) POWER distinction effect boosts every cast (already
    wired, per ``_partition_power_targets``'s null-matches-everything scope gate) — this class
    proves the standalone pull fold now mirrors that (#1834 final-review Finding 2)."""

    def setUp(self) -> None:
        self.resonance = ResonanceFactory(name="Feral")
        self.power_category = ModifierCategoryFactory(name=POWER_CATEGORY_NAME)
        self.power_target = ModifierTargetFactory(
            category=self.power_category,
            name="power_unscoped",
            target_resonance=None,
        )

        self.distinction = DistinctionFactory(name="Raw Might")
        DistinctionEffectFactory(
            distinction=self.distinction,
            target=self.power_target,
            value_per_rank=4,
        )
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        char_distinction = CharacterDistinctionFactory(
            character=self.sheet,
            distinction=self.distinction,
            rank=1,
        )
        create_distinction_modifiers(char_distinction)

    def test_thread_pull_of_arbitrary_resonance_is_boosted_by_unscoped_distinction(self) -> None:
        """Parity with casts: an unscoped POWER effect boosts a pull of ANY resonance."""
        CharacterAnimaFactory(character=self.character, current=10, maximum=10)
        CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=self.resonance,
            balance=10,
            lifetime_earned=10,
        )
        ThreadPullCostFactory(tier=1, resonance_cost=2, anima_per_thread=1)
        thread = ThreadFactory(owner=self.sheet, resonance=self.resonance, level=1)

        preview = preview_resonance_pull(
            self.sheet,
            self.resonance,
            tier=1,
            threads=[thread],
        )

        flat_bonus_total = sum(
            r.scaled_value or 0 for r in preview.resolved_effects if r.kind == EffectKind.FLAT_BONUS
        )
        self.assertEqual(flat_bonus_total, 4)
