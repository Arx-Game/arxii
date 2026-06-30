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
)
from world.covenants.services import release_court_pact, swear_court_pact
from world.magic.constants import TargetKind
from world.magic.factories import ThreadFactory
from world.magic.services import compute_anchor_cap


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
