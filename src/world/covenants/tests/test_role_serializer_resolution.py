"""TDD tests for CharacterCovenantRoleSerializer resolved role surfacing (Task 7).

Tests that the serializer returns the RESOLVED (effective) role in ``covenant_role``
and the stored parent role in ``anchor_role`` — and that a non-promoted membership
returns the parent role in both fields.
"""

from __future__ import annotations

from django.test import TestCase

from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
    SubroleCovenantRoleFactory,
)
from world.covenants.serializers import CharacterCovenantRoleSerializer
from world.magic.constants import TargetKind
from world.magic.factories import ResonanceFactory, ThreadFactory


class RoleSerializerResolutionTests(TestCase):
    """Tests for CharacterCovenantRoleSerializer covenant_role + anchor_role fields."""

    def setUp(self) -> None:
        self.resonance = ResonanceFactory()
        self.parent_role = CovenantRoleFactory()
        # Sub-role unlocks at thread level 3
        self.sub_role = SubroleCovenantRoleFactory(
            parent_role=self.parent_role,
            resonance=self.resonance,
            unlock_thread_level=3,
        )
        self.covenant = CovenantFactory(covenant_type=self.parent_role.covenant_type)

    def _serialize(self, membership):
        """Serialize a membership via CharacterCovenantRoleSerializer."""
        return CharacterCovenantRoleSerializer(membership).data

    def _add_qualifying_thread(self, membership, *, level: int = 3):
        """Create a COVENANT_ROLE thread at *level* for the membership's character."""
        character = membership.character_sheet.character
        ThreadFactory(
            owner=membership.character_sheet,
            resonance=self.resonance,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=self.parent_role,
            target_trait=None,
            level=level,
        )
        character.threads.invalidate()

    def test_promoted_membership_covenant_role_is_subrole(self) -> None:
        """Promoted membership: serialized covenant_role.slug == sub-role slug."""
        membership = CharacterCovenantRoleFactory(
            covenant=self.covenant,
            covenant_role=self.parent_role,
        )
        self._add_qualifying_thread(membership, level=3)
        data = self._serialize(membership)
        self.assertEqual(data["covenant_role"]["slug"], self.sub_role.slug)

    def test_promoted_membership_anchor_role_is_parent(self) -> None:
        """Promoted membership: serialized anchor_role.slug == parent slug."""
        membership = CharacterCovenantRoleFactory(
            covenant=self.covenant,
            covenant_role=self.parent_role,
        )
        self._add_qualifying_thread(membership, level=3)
        data = self._serialize(membership)
        self.assertEqual(data["anchor_role"]["slug"], self.parent_role.slug)

    def test_non_promoted_membership_covenant_role_is_parent(self) -> None:
        """Non-promoted membership: serialized covenant_role.slug == parent slug."""
        membership = CharacterCovenantRoleFactory(
            covenant=self.covenant,
            covenant_role=self.parent_role,
        )
        # No thread → no promotion
        data = self._serialize(membership)
        self.assertEqual(data["covenant_role"]["slug"], self.parent_role.slug)

    def test_non_promoted_membership_anchor_role_is_parent(self) -> None:
        """Non-promoted membership: serialized anchor_role.slug == parent slug."""
        membership = CharacterCovenantRoleFactory(
            covenant=self.covenant,
            covenant_role=self.parent_role,
        )
        data = self._serialize(membership)
        self.assertEqual(data["anchor_role"]["slug"], self.parent_role.slug)

    def test_anchor_role_is_always_stored_parent(self) -> None:
        """anchor_role always reflects the stored (anchored) parent role, never sub-role."""
        membership = CharacterCovenantRoleFactory(
            covenant=self.covenant,
            covenant_role=self.parent_role,
        )
        self._add_qualifying_thread(membership, level=3)
        data = self._serialize(membership)
        # covenant_role resolves to sub-role; anchor_role stays as parent
        self.assertNotEqual(data["covenant_role"]["slug"], data["anchor_role"]["slug"])
        self.assertEqual(data["anchor_role"]["slug"], self.parent_role.slug)
