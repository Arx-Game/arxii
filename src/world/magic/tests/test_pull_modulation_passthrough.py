"""Regression tests for target-aware pull resolution passthrough (#1831 Task 2).

Proves that ``resolve_pull_effects`` gained a ``target`` kwarg with ZERO behavior
change to existing pulls: a target-less COVENANT_ROLE pull and a targeted
non-COVENANT_ROLE pull both resolve to the exact pre-#1831 ``scaled_value``. The
Court-regard modulation rule itself (COVENANT_ROLE + target not None) is built in
Task 3 — this file must never trigger that lazy import.
"""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.factories import CovenantRoleFactory
from world.magic.constants import EffectKind, TargetKind
from world.magic.factories import ThreadFactory, ThreadPullEffectFactory
from world.magic.services.resonance import resolve_pull_effects


class PullModulationPassthroughTests(TestCase):
    """target=None and non-COVENANT_ROLE threads are byte-identical to pre-#1831."""

    def test_covenant_role_pull_with_no_target_is_unchanged(self) -> None:
        """A FLAT_BONUS COVENANT_ROLE pull with target=None resolves unchanged."""
        role = CovenantRoleFactory()
        sheet = CharacterSheetFactory()
        thread = ThreadFactory(
            owner=sheet,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=role,
            target_trait=None,
            level=10,
        )
        ThreadPullEffectFactory(
            target_kind=TargetKind.COVENANT_ROLE,
            resonance=thread.resonance,
            tier=1,
            min_thread_level=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=4,
        )

        resolved = resolve_pull_effects([thread], tier=1, in_combat=True, target=None)

        flat_rows = [r for r in resolved if r.kind == EffectKind.FLAT_BONUS]
        self.assertEqual(len(flat_rows), 1)
        # level=10 -> multiplier = max(1, 10 // 10) = 1; scaled = 4 * 1 = 4.
        self.assertEqual(flat_rows[0].scaled_value, 4)

    def test_non_covenant_role_pull_with_unrelated_target_is_unchanged(self) -> None:
        """A TRAIT-kind (non-COVENANT_ROLE) pull is unaffected by a passed target."""
        target = CharacterSheetFactory().character
        thread = ThreadFactory(level=20)
        ThreadPullEffectFactory(
            target_kind=thread.target_kind,
            resonance=thread.resonance,
            tier=0,
            min_thread_level=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=5,
        )

        resolved = resolve_pull_effects([thread], tier=0, in_combat=False, target=target)

        flat_rows = [r for r in resolved if r.kind == EffectKind.FLAT_BONUS]
        self.assertEqual(len(flat_rows), 1)
        # level=20 -> multiplier = max(1, 20 // 10) = 2; scaled = 5 * 2 = 10.
        self.assertEqual(flat_rows[0].scaled_value, 10)

    def test_default_call_without_target_kwarg_still_works(self) -> None:
        """Existing callers that never pass target= keep working unchanged."""
        thread = ThreadFactory(level=0)
        ThreadPullEffectFactory(
            target_kind=thread.target_kind,
            resonance=thread.resonance,
            tier=0,
            min_thread_level=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=3,
        )

        resolved = resolve_pull_effects([thread], tier=0, in_combat=False)

        flat_rows = [r for r in resolved if r.kind == EffectKind.FLAT_BONUS]
        self.assertEqual(len(flat_rows), 1)
        self.assertEqual(flat_rows[0].scaled_value, 3)
