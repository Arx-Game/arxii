"""Regression: promote_to_subrole does not lower the anchor cap for the parent role.

After a character promotes from parent_role to a sub-role in covenant A,
their historical CCR row (left_at != null, covenant_role=parent_role) still
exists. The max_covenant_level_for_role formula reads ALL rows (active and
historical) for a given role, so the cap on parent_role stays at the
covenant's level even after promotion.
"""

from __future__ import annotations

from django.test import TestCase

from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
    SubroleCovenantRoleFactory,
)
from world.covenants.services import promote_to_subrole
from world.magic.constants import TargetKind
from world.magic.factories import ResonanceFactory, ThreadFactory


class AnchorCapAfterSubrolePromotionTests(TestCase):
    def test_anchor_cap_unchanged_after_subrole_promotion(self) -> None:
        """max_covenant_level_for_role returns the same value before and after promotion.

        Scenario:
          - Character holds parent_role in covenant_a (level=5)
          - Character holds parent_role in covenant_b (level=2)
          - Before promotion: max cap = 5
          - After promotion in covenant_a: old CCR row (level=5) still counts
          - After promotion: max cap still = 5
        """
        parent_role = CovenantRoleFactory()
        resonance = ResonanceFactory()
        subrole = SubroleCovenantRoleFactory(
            parent_role=parent_role,
            resonance=resonance,
            unlock_thread_level=3,
        )

        # covenant_a (level 5) — where promotion will happen
        covenant_a = CovenantFactory(covenant_type=parent_role.covenant_type, level=5)
        membership_a = CharacterCovenantRoleFactory(
            covenant=covenant_a,
            covenant_role=parent_role,
        )

        # covenant_b (level 2) — second membership for the same character + role
        covenant_b = CovenantFactory(covenant_type=parent_role.covenant_type, level=2)
        CharacterCovenantRoleFactory(
            character_sheet=membership_a.character_sheet,
            covenant=covenant_b,
            covenant_role=parent_role,
        )

        character = membership_a.character_sheet.character

        # Thread to satisfy promotion prerequisites
        ThreadFactory(
            owner=membership_a.character_sheet,
            resonance=resonance,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=parent_role,
            target_trait=None,
            level=5,
        )

        # Pre-promotion: cap should be max(5, 2) = 5
        cap_before = character.covenant_roles.max_covenant_level_for_role(parent_role)
        self.assertEqual(cap_before, 5)

        # Promote from parent_role → sub-role in covenant_a
        promote_to_subrole(membership=membership_a, target_subrole=subrole)

        # Post-promotion: the old CCR row (left_at != null, covenant.level=5)
        # still counts in the formula — cap must still be 5
        cap_after = character.covenant_roles.max_covenant_level_for_role(parent_role)
        self.assertEqual(cap_after, 5)

    def test_anchor_cap_reads_historical_row_not_active_role(self) -> None:
        """max_covenant_level_for_role includes ended rows — the formula doesn't filter left_at."""
        parent_role = CovenantRoleFactory()
        resonance = ResonanceFactory()
        subrole = SubroleCovenantRoleFactory(
            parent_role=parent_role,
            resonance=resonance,
            unlock_thread_level=1,
        )

        covenant = CovenantFactory(covenant_type=parent_role.covenant_type, level=10)
        membership = CharacterCovenantRoleFactory(
            covenant=covenant,
            covenant_role=parent_role,
        )
        ThreadFactory(
            owner=membership.character_sheet,
            resonance=resonance,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=parent_role,
            target_trait=None,
            level=3,
        )
        character = membership.character_sheet.character

        # Before promotion: cap = 10
        self.assertEqual(character.covenant_roles.max_covenant_level_for_role(parent_role), 10)

        # Promote; character no longer actively holds parent_role in this covenant
        promote_to_subrole(membership=membership, target_subrole=subrole)

        # Historical row preserved → cap still = 10
        self.assertEqual(character.covenant_roles.max_covenant_level_for_role(parent_role), 10)

        # Verify character actively holds sub-role now (not parent)
        active_role = character.covenant_roles.currently_held_role_in(covenant)
        self.assertEqual(active_role, subrole)
