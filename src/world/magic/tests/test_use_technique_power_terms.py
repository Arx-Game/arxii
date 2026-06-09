"""Tests for use_technique power-term + cast-pull wiring (#768).

Covers the three wiring guarantees added in Task 6:
- passive in-scope threads raise derived power via the thread_power_term,
- a declared cast pull debits resonance currency,
- an unaffordable declared pull raises before the technique's anima is spent.
"""

from types import SimpleNamespace

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import TargetKind
from world.magic.exceptions import ResonanceInsufficient
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterResonanceFactory,
    ResonanceFactory,
    TechniqueFactory,
    ThreadFactory,
    ThreadPullCostFactory,
    ThreadPullEffectFactory,
)
from world.magic.services import use_technique
from world.magic.services.cast_threads import build_cast_applicable_threads
from world.magic.types.pull import CastPullDeclaration
from world.mechanics.factories import CharacterEngagementFactory


def _capture_power() -> "tuple[dict[str, object], object]":
    """Return (captured_dict, resolve_fn) where resolve_fn records the power kwarg."""
    captured: dict[str, object] = {}

    def resolve_fn(*, power: int, ledger: object = None) -> SimpleNamespace:
        captured["power"] = power
        return SimpleNamespace(check_result=None)

    return captured, resolve_fn


class UseTechniqueThreadPowerTermTests(TestCase):
    """A passive TECHNIQUE-anchored thread with a tier-0 INTENSITY_BUMP raises power."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.technique = TechniqueFactory(intensity=5, control=10, anima_cost=2)
        cls.resonance = ResonanceFactory()
        # Tier-0 (always-on passive) INTENSITY_BUMP of 4 for this resonance + kind.
        ThreadPullEffectFactory(
            as_intensity_bump=True,
            target_kind=TargetKind.TECHNIQUE,
            resonance=cls.resonance,
            tier=0,
            intensity_bump_amount=4,
        )

    def _make_caster(self) -> object:
        anima = CharacterAnimaFactory(current=20, maximum=20)
        character = anima.character
        CharacterEngagementFactory(character=character)
        sheet = CharacterSheetFactory(character=character)
        return character, sheet

    def test_passive_thread_raises_power_by_intensity_bump(self) -> None:
        """Derived power == baseline + 4 when the in-scope thread is supplied."""
        # Baseline caster (no thread / no applicable threads).
        baseline_char, _ = self._make_caster()
        baseline_captured, baseline_resolve = _capture_power()
        use_technique(
            character=baseline_char,
            technique=self.technique,
            resolve_fn=baseline_resolve,
            applicable_threads=None,
        )

        # Caster with a TECHNIQUE-anchored thread on this technique.
        thread_char, thread_sheet = self._make_caster()
        ThreadFactory(
            owner=thread_sheet,
            resonance=self.resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_trait=None,
            target_technique=self.technique,
            level=0,
        )
        applicable = build_cast_applicable_threads(thread_sheet, self.technique)
        self.assertTrue(applicable, "thread should be in-scope for the cast")

        thread_captured, thread_resolve = _capture_power()
        use_technique(
            character=thread_char,
            technique=self.technique,
            resolve_fn=thread_resolve,
            applicable_threads=applicable,
        )

        self.assertEqual(
            thread_captured["power"],
            baseline_captured["power"] + 4,
        )


class UseTechniqueCastPullChargeTests(TestCase):
    """A declared cast pull debits resonance currency through use_technique."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.technique = TechniqueFactory(intensity=5, control=10, anima_cost=2)
        cls.resonance = ResonanceFactory()
        # tier-1 pull: 1 resonance, 1 anima per thread.
        ThreadPullCostFactory(tier=1, resonance_cost=1, anima_per_thread=1)

    def setUp(self) -> None:
        self.anima = CharacterAnimaFactory(current=20, maximum=20)
        self.character = self.anima.character
        CharacterEngagementFactory(character=self.character)
        self.sheet = CharacterSheetFactory(character=self.character)
        self.thread = ThreadFactory(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_trait=None,
            target_technique=self.technique,
            level=0,
        )

    def test_declared_pull_debits_resonance(self) -> None:
        cr = CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=self.resonance,
            balance=10,
            lifetime_earned=10,
        )
        _, resolve_fn = _capture_power()

        use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=resolve_fn,
            cast_pull=CastPullDeclaration(resonance=self.resonance, tier=1, threads=(self.thread,)),
        )

        cr.refresh_from_db()
        self.assertEqual(cr.balance, 9)  # 10 - 1 (single thread → no anima cost)


class UseTechniqueUnaffordablePullTests(TestCase):
    """An unaffordable declared pull raises before the technique's anima is spent."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.technique = TechniqueFactory(intensity=5, control=10, anima_cost=2)
        cls.resonance = ResonanceFactory()
        ThreadPullCostFactory(tier=1, resonance_cost=1, anima_per_thread=1)

    def setUp(self) -> None:
        self.anima = CharacterAnimaFactory(current=20, maximum=20)
        self.character = self.anima.character
        CharacterEngagementFactory(character=self.character)
        self.sheet = CharacterSheetFactory(character=self.character)
        self.thread = ThreadFactory(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_trait=None,
            target_technique=self.technique,
            level=0,
        )

    def test_unaffordable_pull_raises_before_anima_spent(self) -> None:
        CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=self.resonance,
            balance=0,
            lifetime_earned=0,
        )
        _, resolve_fn = _capture_power()

        with self.assertRaises(ResonanceInsufficient):
            use_technique(
                character=self.character,
                technique=self.technique,
                resolve_fn=resolve_fn,
                cast_pull=CastPullDeclaration(
                    resonance=self.resonance, tier=1, threads=(self.thread,)
                ),
            )

        # The pull charge precedes deduct_anima, so the technique's own anima
        # must be untouched when the pull raises.
        self.anima.refresh_from_db()
        self.assertEqual(self.anima.current, 20)
