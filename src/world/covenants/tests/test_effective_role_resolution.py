"""Tests for resolve_effective_role and handler routing (Task 2)."""

from __future__ import annotations

from django.test import TestCase
from django.utils import timezone

from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
    SubroleCovenantRoleFactory,
)
from world.covenants.services import resolve_effective_role
from world.magic.constants import TargetKind
from world.magic.factories import ResonanceFactory, ThreadFactory


class ResolveEffectiveRoleTests(TestCase):
    """Tests for the derive-on-read resolve_effective_role service."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.resonance = ResonanceFactory()
        cls.parent_role = CovenantRoleFactory()
        # Sub-role that unlocks at level 3
        cls.sub_role_3 = SubroleCovenantRoleFactory(
            parent_role=cls.parent_role,
            resonance=cls.resonance,
            unlock_thread_level=3,
        )
        cls.covenant = CovenantFactory(covenant_type=cls.parent_role.covenant_type)
        cls.membership = CharacterCovenantRoleFactory(
            covenant=cls.covenant,
            covenant_role=cls.parent_role,
        )
        cls.character = cls.membership.character_sheet.character

    def _make_thread(self, *, level: int, retired: bool = False):
        t = ThreadFactory(
            owner=self.membership.character_sheet,
            resonance=self.resonance,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=self.parent_role,
            target_trait=None,
            level=level,
        )
        if retired:
            t.retired_at = timezone.now()
            t.save(update_fields=["retired_at"])
        # Invalidate thread handler so fresh load sees the new/updated thread
        self.character.threads.invalidate()
        return t

    def test_below_unlock_threshold_returns_parent(self) -> None:
        """Thread level 2 < unlock_thread_level 3 → resolve returns parent."""
        self._make_thread(level=2)
        result = resolve_effective_role(character=self.character, role=self.parent_role)
        self.assertEqual(result, self.parent_role)

    def test_at_unlock_threshold_returns_subrole(self) -> None:
        """Thread level 3 == unlock_thread_level 3 → resolve returns sub_role."""
        self._make_thread(level=3)
        result = resolve_effective_role(character=self.character, role=self.parent_role)
        self.assertEqual(result, self.sub_role_3)

    def test_above_threshold_returns_best_subrole(self) -> None:
        """With two sub-roles at unlock 3 and 5, thread level 5 → unlock-5 sub-role wins."""
        resonance2 = ResonanceFactory()
        sub_role_5 = SubroleCovenantRoleFactory(
            parent_role=self.parent_role,
            resonance=resonance2,
            unlock_thread_level=5,
        )
        membership2 = CharacterCovenantRoleFactory(
            covenant=CovenantFactory(covenant_type=self.parent_role.covenant_type),
            covenant_role=self.parent_role,
        )
        char2 = membership2.character_sheet.character
        ThreadFactory(
            owner=membership2.character_sheet,
            resonance=resonance2,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=self.parent_role,
            target_trait=None,
            level=5,
        )
        char2.threads.invalidate()
        result = resolve_effective_role(character=char2, role=self.parent_role)
        self.assertEqual(result, sub_role_5)

    def test_two_subroles_same_resonance_best_wins(self) -> None:
        """Thread level 5 with two sub-roles at unlock 3 and unlock 5 → unlock-5 sub-role."""
        # Use a fresh parent role so we don't collide with the class-level sub_role_3
        parent = CovenantRoleFactory()
        res = ResonanceFactory()
        sub3 = SubroleCovenantRoleFactory(parent_role=parent, resonance=res, unlock_thread_level=3)
        sub5 = SubroleCovenantRoleFactory(parent_role=parent, resonance=res, unlock_thread_level=5)
        membership = CharacterCovenantRoleFactory(
            covenant=CovenantFactory(covenant_type=parent.covenant_type),
            covenant_role=parent,
        )
        char = membership.character_sheet.character
        ThreadFactory(
            owner=membership.character_sheet,
            resonance=res,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=parent,
            target_trait=None,
            level=5,
        )
        char.threads.invalidate()
        result = resolve_effective_role(character=char, role=parent)
        self.assertEqual(result, sub5)
        self.assertNotEqual(result, sub3)

    def test_no_subrole_for_resonance_returns_parent(self) -> None:
        """Thread exists but no sub-role has that resonance → returns parent."""
        other_res = ResonanceFactory()
        membership = CharacterCovenantRoleFactory(
            covenant=CovenantFactory(covenant_type=self.parent_role.covenant_type),
            covenant_role=self.parent_role,
        )
        char = membership.character_sheet.character
        ThreadFactory(
            owner=membership.character_sheet,
            resonance=other_res,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=self.parent_role,
            target_trait=None,
            level=5,
        )
        char.threads.invalidate()
        result = resolve_effective_role(character=char, role=self.parent_role)
        self.assertEqual(result, self.parent_role)

    def test_retired_thread_returns_parent(self) -> None:
        """Retired thread is ignored → returns parent."""
        membership2 = CharacterCovenantRoleFactory(
            covenant=CovenantFactory(covenant_type=self.parent_role.covenant_type),
            covenant_role=self.parent_role,
        )
        char2 = membership2.character_sheet.character
        t = ThreadFactory(
            owner=membership2.character_sheet,
            resonance=self.resonance,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=self.parent_role,
            target_trait=None,
            level=3,
        )
        t.retired_at = timezone.now()
        t.save(update_fields=["retired_at"])
        char2.threads.invalidate()
        result = resolve_effective_role(character=char2, role=self.parent_role)
        self.assertEqual(result, self.parent_role)

    def test_no_thread_returns_parent(self) -> None:
        """Character with no threads → returns parent."""
        membership2 = CharacterCovenantRoleFactory(
            covenant=CovenantFactory(covenant_type=self.parent_role.covenant_type),
            covenant_role=self.parent_role,
        )
        char2 = membership2.character_sheet.character
        result = resolve_effective_role(character=char2, role=self.parent_role)
        self.assertEqual(result, self.parent_role)

    def test_already_subrole_returns_itself(self) -> None:
        """If role is already a sub-role (has parent_role), return it unchanged."""
        result = resolve_effective_role(character=self.character, role=self.sub_role_3)
        self.assertEqual(result, self.sub_role_3)


class HandlerCurrentlyEngagedRolesResolutionTests(TestCase):
    """handler.currently_engaged_roles() returns resolved sub-role when promoted."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.resonance = ResonanceFactory()
        cls.parent_role = CovenantRoleFactory()
        cls.sub_role = SubroleCovenantRoleFactory(
            parent_role=cls.parent_role,
            resonance=cls.resonance,
            unlock_thread_level=3,
        )
        cls.covenant = CovenantFactory(covenant_type=cls.parent_role.covenant_type)
        cls.membership = CharacterCovenantRoleFactory(
            covenant=cls.covenant,
            covenant_role=cls.parent_role,
        )
        cls.membership.engaged = True
        cls.membership.save(update_fields=["engaged"])
        cls.character = cls.membership.character_sheet.character

    def test_handler_returns_subrole_when_thread_qualifies(self) -> None:
        """Engaged parent role + qualifying thread → currently_engaged_roles returns sub-role."""
        ThreadFactory(
            owner=self.membership.character_sheet,
            resonance=self.resonance,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=self.parent_role,
            target_trait=None,
            level=3,
        )
        self.character.threads.invalidate()
        self.character.covenant_roles.invalidate()

        engaged = self.character.covenant_roles.currently_engaged_roles()
        self.assertEqual(len(engaged), 1)
        self.assertEqual(engaged[0], self.sub_role)

    def test_handler_returns_parent_when_thread_below_threshold(self) -> None:
        """Thread level 2 < unlock 3 → currently_engaged_roles returns parent."""
        ThreadFactory(
            owner=self.membership.character_sheet,
            resonance=self.resonance,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=self.parent_role,
            target_trait=None,
            level=2,
        )
        self.character.threads.invalidate()
        self.character.covenant_roles.invalidate()

        engaged = self.character.covenant_roles.currently_engaged_roles()
        self.assertEqual(len(engaged), 1)
        self.assertEqual(engaged[0], self.parent_role)


class AnchorRoleInHandlerTests(TestCase):
    """anchor_role_in returns the stored parent role (membership's covenant_role)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.resonance = ResonanceFactory()
        cls.parent_role = CovenantRoleFactory()
        cls.sub_role = SubroleCovenantRoleFactory(
            parent_role=cls.parent_role,
            resonance=cls.resonance,
            unlock_thread_level=3,
        )
        cls.covenant = CovenantFactory(covenant_type=cls.parent_role.covenant_type)
        cls.membership = CharacterCovenantRoleFactory(
            covenant=cls.covenant,
            covenant_role=cls.parent_role,
        )
        cls.membership.engaged = True
        cls.membership.save(update_fields=["engaged"])
        cls.character = cls.membership.character_sheet.character

    def test_anchor_role_in_returns_stored_role(self) -> None:
        """anchor_role_in returns membership.covenant_role (the stored/parent role)."""
        role = self.character.covenant_roles.anchor_role_in(self.covenant)
        self.assertEqual(role, self.parent_role)

    def test_anchor_role_in_none_when_not_member(self) -> None:
        """anchor_role_in returns None for a covenant the character isn't in."""
        other_covenant = CovenantFactory()
        role = self.character.covenant_roles.anchor_role_in(other_covenant)
        self.assertIsNone(role)


class PassiveCapabilityGrantAnchorTests(TestCase):
    """passive_capability_grants still gates on the PARENT (anchor) thread after promotion."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import CharacterFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.conditions.factories import CapabilityTypeFactory
        from world.magic.constants import EffectKind
        from world.magic.factories import ThreadPullEffectFactory

        cls.resonance = ResonanceFactory()
        cls.parent_role = CovenantRoleFactory()
        cls.sub_role = SubroleCovenantRoleFactory(
            parent_role=cls.parent_role,
            resonance=cls.resonance,
            unlock_thread_level=3,
        )
        cls.covenant = CovenantFactory(covenant_type=cls.parent_role.covenant_type)

        cls.char_obj = CharacterFactory(db_key="CapGrantAnchorChar")
        cls.sheet = CharacterSheetFactory(character=cls.char_obj, primary_persona=False)

        cls.membership = CharacterCovenantRoleFactory(
            character_sheet=cls.sheet,
            covenant=cls.covenant,
            covenant_role=cls.parent_role,
        )
        cls.membership.engaged = True
        cls.membership.save(update_fields=["engaged"])

        # Thread anchored on parent role (this is what the DB stores)
        cls.thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=cls.parent_role,
            target_trait=None,
            level=5,
        )

        cls.capability = CapabilityTypeFactory()
        cls.effect = ThreadPullEffectFactory(
            target_kind=TargetKind.COVENANT_ROLE,
            resonance=cls.resonance,
            tier=0,
            effect_kind=EffectKind.CAPABILITY_GRANT,
            flat_bonus_amount=None,
            capability_grant=cls.capability,
            min_thread_level=1,
        )

    def test_capability_grant_active_when_engaged_on_parent_role(self) -> None:
        """CAPABILITY_GRANT fires when character is engaged — thread anchors on parent."""
        self.char_obj.threads.invalidate()
        self.char_obj.covenant_roles.invalidate()

        grants = self.char_obj.threads.passive_capability_grants()
        self.assertIn(self.capability.pk, grants)

    def test_capability_grant_active_after_role_resolves_to_subrole(self) -> None:
        """After role resolves to sub-role, CAPABILITY_GRANT still fires (anchor is parent)."""
        # currently_engaged_roles() will return sub_role (thread level 5 >= unlock 3)
        self.char_obj.threads.invalidate()
        self.char_obj.covenant_roles.invalidate()

        # Verify engaged roles returns sub_role
        engaged = self.char_obj.covenant_roles.currently_engaged_roles()
        self.assertEqual(len(engaged), 1)
        self.assertEqual(engaged[0], self.sub_role)

        # But capability grant must still fire (anchor = parent)
        grants = self.char_obj.threads.passive_capability_grants()
        self.assertIn(self.capability.pk, grants)
