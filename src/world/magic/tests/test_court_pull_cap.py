"""Court-role thread-pull cap bounded by the master's granted cap (#1589, Task 6).

When a Court servant pulls their COURT-role thread in combat, the anchor cap is
additionally bounded by ``CourtPact.granted_pull_cap`` — what their master granted
them. Durance/Battle roles are byte-for-byte unaffected.

Semantics: a Court servant with NO active pact (master granted nothing) gets
granted=0 → cap 0 → they cannot pull their Court-role thread. The grant is the gate.
"""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import CovenantType
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
    wire_court_role_powers_catalog,
)
from world.covenants.services import release_court_pact, swear_court_pact
from world.magic.constants import EffectKind, TargetKind
from world.magic.factories import ThreadFactory
from world.magic.services import compute_anchor_cap
from world.magic.services.resonance import resolve_pull_effects


class CourtPullCapTests(TestCase):
    """The COURT arm of compute_anchor_cap bounds by the master's granted cap."""

    @classmethod
    def setUpTestData(cls) -> None:
        # Court covenant at level 3 → base covenant_component = 30 (mult 10).
        # Fresh join (0 days) + no legend → base_cap = 30.
        cls.role = CovenantRoleFactory(covenant_type=CovenantType.COURT)
        cls.covenant = CovenantFactory(covenant_type=CovenantType.COURT, level=3)

    def _servant_with_court_thread(self) -> tuple[CharacterSheetFactory, object]:
        servant = CharacterSheetFactory()
        CharacterCovenantRoleFactory(
            character_sheet=servant, covenant=self.covenant, covenant_role=self.role
        )
        thread = ThreadFactory(
            owner=servant,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=self.role,
            target_trait=None,
        )
        return servant, thread

    def test_grant_caps_below_base(self) -> None:
        """granted_pull_cap=2 with a base cap of 30 → cap is the grant (2)."""
        servant, thread = self._servant_with_court_thread()
        swear_court_pact(covenant=self.covenant, servant_sheet=servant, granted_pull_cap=2)
        self.assertEqual(compute_anchor_cap(thread), 2)

    def test_high_grant_not_binding(self) -> None:
        """granted_pull_cap >= base → base_cap (30) is the binding constraint."""
        servant, thread = self._servant_with_court_thread()
        swear_court_pact(covenant=self.covenant, servant_sheet=servant, granted_pull_cap=50)
        self.assertEqual(compute_anchor_cap(thread), 30)

    def test_no_active_pact_caps_at_zero(self) -> None:
        """No active pact (master granted nothing) → cap 0. The grant is the gate."""
        _servant, thread = self._servant_with_court_thread()
        self.assertEqual(compute_anchor_cap(thread), 0)

    def test_released_pact_caps_at_zero(self) -> None:
        """A released pact does not count → cap 0."""
        servant, thread = self._servant_with_court_thread()
        pact = swear_court_pact(covenant=self.covenant, servant_sheet=servant, granted_pull_cap=5)
        release_court_pact(pact=pact)
        self.assertEqual(compute_anchor_cap(thread), 0)

    def test_durance_role_unaffected_by_pact_logic(self) -> None:
        """A DURANCE-role thread uses the existing formula, untouched by Court logic."""
        durance_role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        durance_covenant = CovenantFactory(covenant_type=CovenantType.DURANCE, level=3)
        servant = CharacterSheetFactory()
        CharacterCovenantRoleFactory(
            character_sheet=servant,
            covenant=durance_covenant,
            covenant_role=durance_role,
        )
        thread = ThreadFactory(
            owner=servant,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=durance_role,
            target_trait=None,
        )
        # base covenant_component only (level 3 → 30); no pact involvement at all.
        self.assertEqual(compute_anchor_cap(thread), 30)


class CourtPullEffectGateTests(TestCase):
    """The pact is the REAL gate on the Court active pull (#1589 final review).

    The seeded Court active-pull effects are authored at ``min_thread_level=1``.
    A no-pact servant gets granted cap 0 → their Court-role thread cannot imbue
    above level 0 → ``resolve_pull_effects`` selects no FLAT_BONUS (the pull yields
    no Court bonus). A servant whose pact lifted the cap (thread level ≥ 1) DOES
    get the FLAT_BONUS. This makes "no pact → cannot pull" structurally true, not
    merely cap-cosmetic.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.role, cls.flat_effects = wire_court_role_powers_catalog()
        cls.resonance = cls.flat_effects[0].resonance
        # The seeded active pull is authored above level 0 — the pact gate.
        for effect in cls.flat_effects:
            assert effect.min_thread_level == 1

    def _court_thread(self, level: int) -> object:
        servant = CharacterSheetFactory()
        return ThreadFactory(
            owner=servant,
            resonance=self.resonance,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=self.role,
            target_trait=None,
            level=level,
        )

    def _flat_bonuses(self, thread: object) -> list:
        resolved = resolve_pull_effects([thread], tier=1, in_combat=True)
        return [e for e in resolved if e.kind == EffectKind.FLAT_BONUS]

    def test_level_zero_thread_yields_no_court_flat_bonus(self) -> None:
        """No pact (cap 0 → thread stuck at level 0) → the pull yields NO FLAT_BONUS."""
        thread = self._court_thread(0)
        self.assertEqual(
            self._flat_bonuses(thread),
            [],
            "A level-0 Court-role thread must pull no FLAT_BONUS — the pact is the gate.",
        )

    def test_level_one_thread_yields_court_flat_bonus(self) -> None:
        """With a pact lifting the cap (thread level ≥ 1) the FLAT_BONUS applies."""
        thread = self._court_thread(1)
        flat = self._flat_bonuses(thread)
        self.assertTrue(
            flat,
            "A level-1 Court-role thread must pull the seeded FLAT_BONUS.",
        )
        self.assertGreater(flat[0].scaled_value, 0)
