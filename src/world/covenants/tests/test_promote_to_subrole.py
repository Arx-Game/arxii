"""Tests for the promote_to_subrole service (Task 7)."""

from __future__ import annotations

from django.test import TestCase

from world.covenants.exceptions import (
    SubroleParentMismatchError,
    SubroleResonanceMismatchError,
    SubroleThreadLevelInsufficientError,
)
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
    SubroleCovenantRoleFactory,
)
from world.covenants.models import CharacterCovenantRole
from world.covenants.services import promote_to_subrole
from world.magic.constants import TargetKind
from world.magic.factories import ResonanceFactory, ThreadFactory


class PromoteToSubroleTests(TestCase):
    def _make_membership_with_thread(
        self,
        *,
        thread_level: int = 5,
        resonance=None,
        parent_role=None,
    ):
        """Helper: create membership + a COVENANT_ROLE Thread anchored on the parent_role.

        Returns (membership, subrole, thread).
        """
        parent_role = parent_role or CovenantRoleFactory()
        resonance = resonance or ResonanceFactory()
        subrole = SubroleCovenantRoleFactory(
            parent_role=parent_role,
            resonance=resonance,
            unlock_thread_level=3,
        )
        covenant = CovenantFactory(covenant_type=parent_role.covenant_type)
        membership = CharacterCovenantRoleFactory(
            covenant=covenant,
            covenant_role=parent_role,
        )
        # Create a COVENANT_ROLE Thread anchored on parent_role with matching resonance
        thread = ThreadFactory(
            owner=membership.character_sheet,
            resonance=resonance,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=parent_role,
            target_trait=None,
            level=thread_level,
        )
        return membership, subrole, thread

    def test_promote_when_all_conditions_met(self) -> None:
        """Happy path: promotion creates new membership and closes old one."""
        membership, subrole, _thread = self._make_membership_with_thread(thread_level=5)

        new_membership = promote_to_subrole(membership=membership, target_subrole=subrole)

        self.assertIsInstance(new_membership, CharacterCovenantRole)
        self.assertEqual(new_membership.covenant_role, subrole)
        self.assertEqual(new_membership.covenant, membership.covenant)
        self.assertEqual(new_membership.character_sheet, membership.character_sheet)
        self.assertIsNone(new_membership.left_at)

    def test_closes_old_membership(self) -> None:
        """After promotion, the old membership row has left_at set."""
        membership, subrole, _thread = self._make_membership_with_thread(thread_level=5)
        old_pk = membership.pk

        promote_to_subrole(membership=membership, target_subrole=subrole)

        old_row = CharacterCovenantRole.objects.get(pk=old_pk)
        self.assertIsNotNone(old_row.left_at)

    def test_raises_parent_mismatch(self) -> None:
        """target_subrole.parent_role != membership.covenant_role raises an error."""
        parent_role = CovenantRoleFactory()
        other_role = CovenantRoleFactory()
        resonance = ResonanceFactory()
        # subrole whose parent is other_role, not parent_role
        subrole = SubroleCovenantRoleFactory(parent_role=other_role, resonance=resonance)
        covenant = CovenantFactory(covenant_type=parent_role.covenant_type)
        membership = CharacterCovenantRoleFactory(covenant=covenant, covenant_role=parent_role)

        with self.assertRaises(SubroleParentMismatchError):
            promote_to_subrole(membership=membership, target_subrole=subrole)

    def test_raises_resonance_mismatch(self) -> None:
        """Character has Thread on parent_role but with a different resonance."""
        parent_role = CovenantRoleFactory()
        subrole_resonance = ResonanceFactory()
        thread_resonance = ResonanceFactory()
        subrole = SubroleCovenantRoleFactory(
            parent_role=parent_role,
            resonance=subrole_resonance,
            unlock_thread_level=3,
        )
        covenant = CovenantFactory(covenant_type=parent_role.covenant_type)
        membership = CharacterCovenantRoleFactory(covenant=covenant, covenant_role=parent_role)
        # Thread anchored on parent_role but with DIFFERENT resonance
        ThreadFactory(
            owner=membership.character_sheet,
            resonance=thread_resonance,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=parent_role,
            target_trait=None,
            level=5,
        )

        with self.assertRaises(SubroleResonanceMismatchError):
            promote_to_subrole(membership=membership, target_subrole=subrole)

    def test_raises_thread_level_insufficient(self) -> None:
        """Thread level 2 when unlock_thread_level=3 raises SubroleThreadLevelInsufficientError."""
        resonance = ResonanceFactory()
        parent_role = CovenantRoleFactory()
        subrole = SubroleCovenantRoleFactory(
            parent_role=parent_role,
            resonance=resonance,
            unlock_thread_level=3,
        )
        covenant = CovenantFactory(covenant_type=parent_role.covenant_type)
        membership = CharacterCovenantRoleFactory(covenant=covenant, covenant_role=parent_role)
        # Thread level 2, but subrole requires level 3
        ThreadFactory(
            owner=membership.character_sheet,
            resonance=resonance,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=parent_role,
            target_trait=None,
            level=2,
        )

        with self.assertRaises(SubroleThreadLevelInsufficientError):
            promote_to_subrole(membership=membership, target_subrole=subrole)

    def test_preserves_engaged_flag_true(self) -> None:
        """engaged=True before promotion → new membership is also engaged."""
        membership, subrole, _thread = self._make_membership_with_thread(thread_level=5)
        membership.engaged = True
        membership.save(update_fields=["engaged"])

        new_membership = promote_to_subrole(membership=membership, target_subrole=subrole)

        self.assertTrue(new_membership.engaged)

    def test_preserves_engaged_flag_false(self) -> None:
        """engaged=False before promotion → new membership is also not engaged."""
        membership, subrole, _thread = self._make_membership_with_thread(thread_level=5)
        # engaged defaults to False in CharacterCovenantRoleFactory

        new_membership = promote_to_subrole(membership=membership, target_subrole=subrole)

        self.assertFalse(new_membership.engaged)

    def test_no_thread_raises_resonance_mismatch(self) -> None:
        """Character with no threads at all raises SubroleResonanceMismatchError."""
        parent_role = CovenantRoleFactory()
        resonance = ResonanceFactory()
        subrole = SubroleCovenantRoleFactory(
            parent_role=parent_role,
            resonance=resonance,
            unlock_thread_level=3,
        )
        covenant = CovenantFactory(covenant_type=parent_role.covenant_type)
        membership = CharacterCovenantRoleFactory(covenant=covenant, covenant_role=parent_role)
        # No threads at all

        with self.assertRaises(SubroleResonanceMismatchError):
            promote_to_subrole(membership=membership, target_subrole=subrole)

    def test_thread_exact_level_meets_threshold(self) -> None:
        """Thread level exactly equal to unlock_thread_level succeeds."""
        resonance = ResonanceFactory()
        parent_role = CovenantRoleFactory()
        subrole = SubroleCovenantRoleFactory(
            parent_role=parent_role,
            resonance=resonance,
            unlock_thread_level=3,
        )
        covenant = CovenantFactory(covenant_type=parent_role.covenant_type)
        membership = CharacterCovenantRoleFactory(covenant=covenant, covenant_role=parent_role)
        ThreadFactory(
            owner=membership.character_sheet,
            resonance=resonance,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=parent_role,
            target_trait=None,
            level=3,  # exactly at the threshold
        )

        new_membership = promote_to_subrole(membership=membership, target_subrole=subrole)

        self.assertEqual(new_membership.covenant_role, subrole)

    def test_handler_cache_invalidated(self) -> None:
        """After promotion, covenant_roles handler sees the new sub-role membership."""
        membership, subrole, _thread = self._make_membership_with_thread(thread_level=5)
        character = membership.character_sheet.character
        covenant = membership.covenant

        promote_to_subrole(membership=membership, target_subrole=subrole)

        current_role = character.covenant_roles.currently_held_role_in(covenant)
        self.assertEqual(current_role, subrole)
