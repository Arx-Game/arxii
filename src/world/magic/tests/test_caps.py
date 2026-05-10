"""Tests for cap helpers: compute_anchor_cap, compute_path_cap, compute_effective_cap.

Spec A §2.4. TDD: written before the implementation.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import TargetKind
from world.magic.exceptions import AnchorCapNotImplemented
from world.magic.factories import ThreadFactory
from world.magic.services import compute_anchor_cap, compute_effective_cap, compute_path_cap


class AnchorCapTests(TestCase):
    def test_trait_cap_equals_trait_value(self) -> None:
        thread = ThreadFactory(as_trait_thread=True, _trait_value=50)
        self.assertEqual(compute_anchor_cap(thread), 50)

    def test_technique_cap_level_times_ten(self) -> None:
        thread = ThreadFactory(as_technique_thread=True, _technique_level=3)
        self.assertEqual(compute_anchor_cap(thread), 30)

    def test_relationship_track_cap_zero_when_no_developed_points(self) -> None:
        # Default developed_points is 0; _developed_points=0 documents intent.
        thread = ThreadFactory(as_track_thread=True, _developed_points=0)
        self.assertEqual(compute_anchor_cap(thread), 0)

    def test_relationship_track_cap_reflects_developed_points_continuously(self) -> None:
        """anchor_cap = developed_points directly. Every point matters, not just tier thresholds."""
        thread = ThreadFactory(as_track_thread=True, _developed_points=37)
        self.assertEqual(compute_anchor_cap(thread), 37)

    def test_relationship_track_cap_scales_with_deeper_relationships(self) -> None:
        thread = ThreadFactory(as_track_thread=True, _developed_points=500)
        self.assertEqual(compute_anchor_cap(thread), 500)

    def test_relationship_capstone_cap_zero_when_capstone_has_no_points(self) -> None:
        # _capstone_points=0 explicitly overrides RelationshipCapstoneFactory's default of 100.
        thread = ThreadFactory(as_capstone_thread=True, _capstone_points=0)
        self.assertEqual(compute_anchor_cap(thread), 0)

    def test_relationship_capstone_cap_reflects_capstone_points(self) -> None:
        """anchor_cap = target_capstone.points. Capstone significance drives Thread cap."""
        thread = ThreadFactory(as_capstone_thread=True, _capstone_points=50)
        self.assertEqual(compute_anchor_cap(thread), 50)

    def test_relationship_capstone_cap_scales_with_capstone_size(self) -> None:
        thread = ThreadFactory(as_capstone_thread=True, _capstone_points=500)
        self.assertEqual(compute_anchor_cap(thread), 500)

    def test_room_raises_not_implemented(self) -> None:
        thread = ThreadFactory(as_room_thread=True)
        with self.assertRaises(AnchorCapNotImplemented):
            compute_anchor_cap(thread)


class CovenantRoleAnchorCapTests(TestCase):
    """COVENANT_ROLE anchor cap reads from membership covenant.level (Slice A §3.5).

    Cap is persistent (independent of engagement). max(covenant.level across all
    CCR rows, active or historical) × 10.
    """

    def test_returns_zero_when_no_membership(self) -> None:
        thread = ThreadFactory(as_covenant_role_thread=True)
        # No CharacterCovenantRole rows for this owner+role pair → cap = 0
        self.assertEqual(compute_anchor_cap(thread), 0)

    def test_returns_max_level_times_ten(self) -> None:
        from world.covenants.constants import CovenantType
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            CovenantFactory,
            CovenantRoleFactory,
        )

        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        cov_a = CovenantFactory(covenant_type=CovenantType.DURANCE, level=4)
        cov_b = CovenantFactory(covenant_type=CovenantType.DURANCE, level=7)
        for cov in (cov_a, cov_b):
            CharacterCovenantRoleFactory(character_sheet=sheet, covenant=cov, covenant_role=role)
        # ThreadFactory needs to use the SAME role and a sheet that already has rows.
        thread = ThreadFactory(
            owner=sheet,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=role,
            target_trait=None,
        )
        self.assertEqual(compute_anchor_cap(thread), 70)

    def test_independent_of_engagement(self) -> None:
        """Cap is a persistent property; engagement does not change it."""
        from world.covenants.factories import make_engaged_member
        from world.covenants.services import clear_engaged_membership

        m = make_engaged_member()
        thread = ThreadFactory(
            owner=m.character_sheet,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=m.covenant_role,
            target_trait=None,
        )
        cap_engaged = compute_anchor_cap(thread)
        clear_engaged_membership(membership=m)
        # Invalidate handler cache to force re-read
        m.character_sheet.character.covenant_roles.invalidate()
        cap_disengaged = compute_anchor_cap(thread)
        self.assertEqual(cap_engaged, cap_disengaged)


class PathCapTests(TestCase):
    def test_no_path_history_returns_ten(self) -> None:
        sheet = CharacterSheetFactory()
        self.assertEqual(compute_path_cap(sheet), 10)

    def test_stage_n_returns_n_times_ten(self) -> None:
        sheet = CharacterSheetFactory(_path_stage=3)
        self.assertEqual(compute_path_cap(sheet), 30)


class EffectiveCapTests(TestCase):
    def test_returns_min_of_path_and_anchor(self) -> None:
        # anchor=50 (technique level 5 × 10), path=20 (stage 2 × 10) → 20
        thread = ThreadFactory(as_technique_thread=True, _technique_level=5, _path_stage=2)
        self.assertEqual(compute_effective_cap(thread), 20)
