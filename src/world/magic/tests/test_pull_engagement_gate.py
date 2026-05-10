"""Tests for COVENANT_ROLE Thread pull eligibility gating on engagement.

Spec 2026-05-09 §3.6, §4.12 — pull allowed only if the character is currently
engaged with a covenant where they hold the anchored role.
"""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import CovenantType
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
    make_engaged_member,
)
from world.covenants.services import (
    clear_engaged_membership,
    set_engaged_membership,
)
from world.magic.constants import TargetKind
from world.magic.exceptions import CovenantRoleNotEngagedError, InvalidImbueAmount
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterResonanceFactory,
    ResonanceFactory,
    ThreadFactory,
    ThreadPullCostFactory,
)
from world.magic.services.resonance import _anchor_in_action, spend_resonance_for_pull
from world.magic.types import PullActionContext


def _make_pull_ctx() -> PullActionContext:
    """Build a minimal PullActionContext (involved_* tuples empty)."""
    return PullActionContext()


class CovenantRolePullGateTests(TestCase):
    """ANY-match: pull allowed if the character is engaged with any covenant
    where they hold the role."""

    def test_no_membership_returns_false(self) -> None:
        """No CCR rows for this role → not in action → predicate returns False."""
        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory()
        thread = ThreadFactory(
            owner=sheet,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=role,
            target_trait=None,
        )
        self.assertFalse(_anchor_in_action(thread, _make_pull_ctx()))

    def test_active_but_not_engaged_returns_false(self) -> None:
        """Active membership but engaged=False → predicate returns False."""
        sheet = CharacterSheetFactory()
        cov = CovenantFactory()
        role = CovenantRoleFactory(covenant_type=cov.covenant_type)
        CharacterCovenantRoleFactory(character_sheet=sheet, covenant=cov, covenant_role=role)
        thread = ThreadFactory(
            owner=sheet,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=role,
            target_trait=None,
        )
        self.assertFalse(_anchor_in_action(thread, _make_pull_ctx()))

    def test_engaged_for_target_role_returns_true(self) -> None:
        """Engaged membership matching the Thread's role → True."""
        m = make_engaged_member()
        thread = ThreadFactory(
            owner=m.character_sheet,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=m.covenant_role,
            target_trait=None,
        )
        self.assertTrue(_anchor_in_action(thread, _make_pull_ctx()))

    def test_engaged_for_different_role_returns_false(self) -> None:
        """Engaged but the Thread's anchor role is different → False."""
        sheet = CharacterSheetFactory()
        make_engaged_member(character_sheet=sheet)
        other_role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        thread = ThreadFactory(
            owner=sheet,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=other_role,
            target_trait=None,
        )
        self.assertFalse(_anchor_in_action(thread, _make_pull_ctx()))

    def test_engaged_in_different_covenant_same_role_returns_true(self) -> None:
        """Two covenants, same role, only one engaged → ANY-match returns True."""
        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        cov_a = CovenantFactory(covenant_type=CovenantType.DURANCE)
        cov_b = CovenantFactory(covenant_type=CovenantType.DURANCE)
        m_a = CharacterCovenantRoleFactory(
            character_sheet=sheet, covenant=cov_a, covenant_role=role
        )
        CharacterCovenantRoleFactory(character_sheet=sheet, covenant=cov_b, covenant_role=role)
        # Engage cov_a only, leave cov_b dormant
        set_engaged_membership(membership=m_a)
        sheet.character.covenant_roles.invalidate()
        thread = ThreadFactory(
            owner=sheet,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=role,
            target_trait=None,
        )
        self.assertTrue(_anchor_in_action(thread, _make_pull_ctx()))

    def test_disengaging_flips_predicate_to_false(self) -> None:
        """After clear_engaged_membership, predicate flips to False (cache invalidated)."""
        m = make_engaged_member()
        thread = ThreadFactory(
            owner=m.character_sheet,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=m.covenant_role,
            target_trait=None,
        )
        self.assertTrue(_anchor_in_action(thread, _make_pull_ctx()))
        clear_engaged_membership(membership=m)
        m.character_sheet.character.covenant_roles.invalidate()
        self.assertFalse(_anchor_in_action(thread, _make_pull_ctx()))


class CovenantRolePullRaisesTypedErrorTests(TestCase):
    """spend_resonance_for_pull raises CovenantRoleNotEngagedError on disengaged COVENANT_ROLE."""

    def test_pull_raises_typed_error_when_not_engaged(self) -> None:
        """Active-but-not-engaged COVENANT_ROLE thread raises CovenantRoleNotEngagedError."""
        sheet = CharacterSheetFactory()
        cov = CovenantFactory()
        role = CovenantRoleFactory(covenant_type=cov.covenant_type)
        # Active but not engaged
        CharacterCovenantRoleFactory(character_sheet=sheet, covenant=cov, covenant_role=role)
        resonance = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=sheet, resonance=resonance, balance=100, lifetime_earned=100
        )
        CharacterAnimaFactory(character=sheet.character, current=100, maximum=100)
        ThreadPullCostFactory(tier=1, resonance_cost=1, anima_per_thread=1)

        thread = ThreadFactory(
            owner=sheet,
            resonance=resonance,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=role,
            target_trait=None,
        )

        with self.assertRaises(CovenantRoleNotEngagedError):
            spend_resonance_for_pull(
                character_sheet=sheet,
                resonance=resonance,
                threads=[thread],
                tier=1,
                action_context=_make_pull_ctx(),
            )

    def test_pull_raises_typed_error_not_generic_invalid_imbue(self) -> None:
        """Verify the typed error is a subclass of InvalidImbueAmount but distinct."""
        self.assertTrue(issubclass(CovenantRoleNotEngagedError, InvalidImbueAmount))
        err = CovenantRoleNotEngagedError()
        self.assertEqual(err.user_message, "You're not currently fulfilling this covenant role.")
