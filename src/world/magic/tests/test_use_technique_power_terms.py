"""Tests for use_technique power-term + cast-pull wiring (#768, #1455).

Covers the three wiring guarantees added in Task 6:
- passive in-scope threads raise derived power via the thread_power_term,
- a declared cast pull debits resonance currency,
- an unaffordable declared pull raises before the technique's anima is spent.

And the two wiring guarantees added in Task 2 (#1455):
- a declared pull with INTENSITY_BUMP effect raises the cast's derived power,
- a declared pull with FLAT_BONUS effect raises the cast check's extra_modifiers,
- a TECHNIQUE_PRE_CAST cancellation does NOT charge the pull (resonance balance
  unchanged), restoring the invariant that aborted casts never spend resources.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from django.test import TestCase
from evennia.objects.models import ObjectDB

from flows.constants import EventName
from flows.consts import FlowActionChoices
from flows.factories import FlowDefinitionFactory, FlowStepDefinitionFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import ReactiveConditionFactory
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


def _create_room(key: str = "TestRoom") -> ObjectDB:
    return ObjectDB.objects.create(
        db_key=key,
        db_typeclass_path="typeclasses.rooms.Room",
    )


def _make_cancel_flow():
    """Return a FlowDefinition with a single CANCEL_EVENT step."""
    flow = FlowDefinitionFactory()
    FlowStepDefinitionFactory(
        flow=flow,
        parent_id=None,
        action=FlowActionChoices.CANCEL_EVENT,
        parameters={},
    )
    return flow


def _capture_power() -> "tuple[dict[str, object], object]":
    """Return (captured_dict, resolve_fn) recording power and extra_modifiers kwargs."""
    captured: dict[str, object] = {}

    def resolve_fn(
        *, power: int, ledger: object = None, extra_modifiers: int = 0
    ) -> SimpleNamespace:
        captured["power"] = power
        captured["extra_modifiers"] = extra_modifiers
        return SimpleNamespace(check_result=None)

    return captured, resolve_fn


def _make_caster() -> "tuple[object, object]":
    """Create a caster (ObjectDB) + CharacterSheet with full anima and engagement."""
    anima = CharacterAnimaFactory(current=20, maximum=20)
    character = anima.character
    CharacterEngagementFactory(character=character)
    sheet = CharacterSheetFactory(character=character)
    return character, sheet


def _make_technique_thread(sheet: object, resonance: object, technique: object) -> object:
    """Create a tier-0 TECHNIQUE-anchored thread on ``technique`` owned by ``sheet``."""
    return ThreadFactory(
        owner=sheet,
        resonance=resonance,
        target_kind=TargetKind.TECHNIQUE,
        target_trait=None,
        target_technique=technique,
        level=0,
    )


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

    def test_passive_thread_raises_power_by_intensity_bump(self) -> None:
        """Derived power == baseline + 4 when the in-scope thread is supplied."""
        # Baseline caster (no thread / no applicable threads).
        baseline_char, _ = _make_caster()
        baseline_captured, baseline_resolve = _capture_power()
        use_technique(
            character=baseline_char,
            technique=self.technique,
            resolve_fn=baseline_resolve,
            applicable_threads=None,
        )

        # Caster with a TECHNIQUE-anchored thread on this technique.
        thread_char, thread_sheet = _make_caster()
        _make_technique_thread(thread_sheet, self.resonance, self.technique)
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


class _CastPullChargeTestBase(TestCase):
    """Shared setup: a known technique + resonance with a tier-1 pull cost, and a
    caster owning a TECHNIQUE-anchored thread on that technique."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.technique = TechniqueFactory(intensity=5, control=10, anima_cost=2)
        cls.resonance = ResonanceFactory()
        # tier-1 pull: 1 resonance, 1 anima per thread.
        ThreadPullCostFactory(tier=1, resonance_cost=1, anima_per_thread=1)
        # tier-1 FLAT_BONUS so the pull has at least one applicable effect (guard
        # added by #1455 refuses pulls where every resolved effect is inactive).
        ThreadPullEffectFactory(
            target_kind=TargetKind.TECHNIQUE,
            resonance=cls.resonance,
            tier=1,
            flat_bonus_amount=2,
        )

    def setUp(self) -> None:
        self.character, self.sheet = _make_caster()
        self.anima = self.character.anima
        self.thread = _make_technique_thread(self.sheet, self.resonance, self.technique)


class UseTechniqueCastPullChargeTests(_CastPullChargeTestBase):
    """A declared cast pull debits resonance currency through use_technique."""

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


class UseTechniqueUnaffordablePullTests(_CastPullChargeTestBase):
    """An unaffordable declared pull raises before the technique's anima is spent."""

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


class _CastPullIntensityTestBase(TestCase):
    """Shared setup for INTENSITY_BUMP pull tests: a technique + resonance with a
    tier-1 INTENSITY_BUMP pull effect and a TECHNIQUE-anchored thread."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.technique = TechniqueFactory(intensity=5, control=10, anima_cost=2)
        cls.resonance = ResonanceFactory()
        # tier-1 pull cost row.
        ThreadPullCostFactory(tier=1, resonance_cost=1, anima_per_thread=1)
        # tier-1 INTENSITY_BUMP of 3 for TECHNIQUE-anchored threads.
        ThreadPullEffectFactory(
            as_intensity_bump=True,
            target_kind=TargetKind.TECHNIQUE,
            resonance=cls.resonance,
            tier=1,
            intensity_bump_amount=3,
        )

    def setUp(self) -> None:
        self.character, self.sheet = _make_caster()
        self.thread = _make_technique_thread(self.sheet, self.resonance, self.technique)


class UseTechniqueIntensityPullTests(_CastPullIntensityTestBase):
    """A declared pull with INTENSITY_BUMP raises the cast's derived power (#1455 Task 2)."""

    def test_noncombat_cast_intensity_pull_raises_power(self) -> None:
        """Derived power with an INTENSITY_BUMP pull exceeds the baseline without a pull."""
        CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=self.resonance,
            balance=10,
            lifetime_earned=10,
        )

        # Baseline: no pull declared.
        baseline_captured, baseline_resolve = _capture_power()
        use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=baseline_resolve,
        )
        baseline_power = baseline_captured["power"]

        # Create a fresh caster (anima already spent on baseline).
        char2, sheet2 = _make_caster()
        thread2 = _make_technique_thread(sheet2, self.resonance, self.technique)
        CharacterResonanceFactory(
            character_sheet=sheet2,
            resonance=self.resonance,
            balance=10,
            lifetime_earned=10,
        )

        # Pull declared with INTENSITY_BUMP=3.
        pulled_captured, pulled_resolve = _capture_power()
        use_technique(
            character=char2,
            technique=self.technique,
            resolve_fn=pulled_resolve,
            cast_pull=CastPullDeclaration(resonance=self.resonance, tier=1, threads=(thread2,)),
        )
        pulled_power = pulled_captured["power"]

        self.assertGreater(
            pulled_power,
            baseline_power,
            f"Expected pulled power {pulled_power} > baseline {baseline_power}",
        )


class UseTechniqueFlatPullTests(_CastPullChargeTestBase):
    """A declared pull with FLAT_BONUS raises the cast check's extra_modifiers (#1455 Task 2).

    Reuses _CastPullChargeTestBase which already creates a tier-1 FLAT_BONUS effect
    with flat_bonus_amount=2 (→ scaled_value=2 for a level-0 thread).
    """

    def test_noncombat_cast_flat_pull_raises_check_modifier(self) -> None:
        """extra_modifiers delivered to resolve_fn == the FLAT_BONUS scaled_value."""
        CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=self.resonance,
            balance=10,
            lifetime_earned=10,
        )

        captured, resolve_fn = _capture_power()
        use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=resolve_fn,
            cast_pull=CastPullDeclaration(resonance=self.resonance, tier=1, threads=(self.thread,)),
        )

        # flat_bonus_amount=2, level=0 → multiplier=max(1,0//10)=1 → scaled_value=2.
        self.assertEqual(
            captured["extra_modifiers"],
            2,
            "Expected extra_modifiers == 2 from FLAT_BONUS pull effect",
        )


class UseTechniqueCancelledPreCastPullTests(_CastPullChargeTestBase):
    """A TECHNIQUE_PRE_CAST cancellation must NOT charge the pull (#1455 regression lock).

    The pull charge was previously placed before the pre-cast cancellation gate, which
    meant a reactive subscriber cancelling the cast would still spend the caster's
    resonance. This test locks the restored invariant: resonance balance must be
    identical before and after a cancelled cast.

    Uses _CastPullChargeTestBase which already provides a tier-1 FLAT_BONUS pull effect
    (non-inert) and a TECHNIQUE-anchored thread. A room is required for the
    TECHNIQUE_PRE_CAST event to fire and for the cancel trigger to activate.
    """

    SELF_FILTER = {"path": "caster", "op": "==", "value": "self"}

    def setUp(self) -> None:
        super().setUp()
        self.room = _create_room()
        self.character.location = self.room

    def test_cancelled_precast_does_not_charge_pull(self) -> None:
        """Resonance balance is unchanged when TECHNIQUE_PRE_CAST is cancelled."""
        cr = CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=self.resonance,
            balance=10,
            lifetime_earned=10,
        )
        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventName.TECHNIQUE_PRE_CAST,
            filter_condition=self.SELF_FILTER,
            flow_definition=cancel_flow,
            target=self.character,
        )

        result = use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=MagicMock(return_value="result"),
            cast_pull=CastPullDeclaration(resonance=self.resonance, tier=1, threads=(self.thread,)),
        )

        self.assertFalse(result.confirmed, "cast should be cancelled, not confirmed")
        cr.refresh_from_db()
        self.assertEqual(
            cr.balance,
            10,
            "resonance balance must be unchanged when cast is cancelled",
        )
