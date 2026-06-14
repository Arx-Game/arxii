"""Tests for thread-passive capability grants in the conditions read path (#751 / B2).

Task B1 added ``CharacterThreadHandler.passive_capability_grants()`` (the single
source of thread-passive CapabilityType grants, engagement-gated). B2 folds that
result into the canonical capability read so gameplay actually sees the grant:

- ``get_effective_capability_value`` (intrinsic/agency read) gains a +1 floor per
  granted capability.
- ``get_all_capability_values`` (bulk dict, consumed by the obstacle/action system)
  surfaces granted PKs at value >= 1 EVEN when the character has no active conditions.

A passive grant means the capability is POSSESSED → it contributes a value floor of
1, additive with other sources (it never clobbers a higher existing value).
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import CapabilityTypeFactory
from world.conditions.services import (
    get_all_capability_values,
    get_effective_capability_value,
)
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
)
from world.magic.constants import EffectKind, TargetKind
from world.magic.factories import (
    ResonanceFactory,
    ThreadFactory,
    ThreadPullEffectFactory,
)


class ThreadPassiveCapabilitySourceTests(TestCase):
    """Engaged tier-0 CAPABILITY_GRANT role threads surface in the capability read."""

    def _build(self, *, engaged: bool):
        """Build a character + engaged/unengaged tier-0 role CAPABILITY_GRANT.

        Mirrors the B1 chain (see magic/tests/test_passive_capability_grants.py):
        CovenantRole + Resonance + COVENANT_ROLE Thread + tier-0 capability_grant
        ThreadPullEffect + a CharacterCovenantRole engagement record.
        Returns (sheet, capability).
        """
        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory()
        resonance = ResonanceFactory()
        cap = CapabilityTypeFactory()

        ThreadFactory(
            owner=sheet,
            resonance=resonance,
            target_kind=TargetKind.COVENANT_ROLE,
            target_trait=None,
            target_covenant_role=role,
            level=10,
        )
        ThreadPullEffectFactory(
            target_kind=TargetKind.COVENANT_ROLE,
            resonance=resonance,
            tier=0,
            min_thread_level=0,
            effect_kind=EffectKind.CAPABILITY_GRANT,
            flat_bonus_amount=None,
            capability_grant=cap,
        )
        CharacterCovenantRoleFactory(
            character_sheet=sheet,
            covenant=CovenantFactory(),
            covenant_role=role,
            engaged=engaged,
            left_at=None,
        )
        return sheet, cap

    def test_engaged_role_grant_raises_effective_capability(self) -> None:
        sheet, cap = self._build(engaged=True)
        self.assertGreaterEqual(get_effective_capability_value(sheet, cap), 1)

    def test_engaged_role_grant_appears_in_all_capability_values(self) -> None:
        sheet, cap = self._build(engaged=True)
        # No active conditions on this character — the grant must still surface.
        values = get_all_capability_values(sheet)
        self.assertIn(cap.pk, values)
        self.assertGreaterEqual(values[cap.pk], 1)

    def test_no_grant_without_engagement(self) -> None:
        sheet, cap = self._build(engaged=False)
        self.assertEqual(get_effective_capability_value(sheet, cap), cap.innate_baseline)
        self.assertNotIn(cap.pk, get_all_capability_values(sheet))
