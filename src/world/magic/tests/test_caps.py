"""Tests for cap helpers: compute_anchor_cap, compute_path_cap, compute_effective_cap.

Spec A §2.4. TDD: written before the implementation.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import SanctumSlotKind, TargetKind
from world.magic.factories import ResonanceFactory, ThreadFactory
from world.magic.models import SanctumDetails, SanctumOwnerMode
from world.magic.services import compute_anchor_cap, compute_effective_cap, compute_path_cap
from world.room_features.factories import RoomFeatureInstanceFactory, RoomFeatureKindFactory


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

    def test_sanctum_anchor_cap_is_level_times_ten(self) -> None:
        """SANCTUM thread cap = sanctum feature_instance.level × 10 (Plan 4 §F)."""
        sanctum = SanctumDetails.objects.create(
            feature_instance=RoomFeatureInstanceFactory(
                feature_kind=RoomFeatureKindFactory(), level=3
            ),
            resonance_type=ResonanceFactory(),
            owner_mode=SanctumOwnerMode.PERSONAL,
        )
        thread = ThreadFactory(
            target_kind=TargetKind.SANCTUM,
            target_trait=None,
            target_sanctum_details=sanctum,
            slot_kind=SanctumSlotKind.PERSONAL_OWN,
        )
        self.assertEqual(compute_anchor_cap(thread), 30)

    def test_sanctum_anchor_cap_level_one(self) -> None:
        """SANCTUM level 1 → cap 10."""
        sanctum = SanctumDetails.objects.create(
            feature_instance=RoomFeatureInstanceFactory(
                feature_kind=RoomFeatureKindFactory(), level=1
            ),
            resonance_type=ResonanceFactory(),
            owner_mode=SanctumOwnerMode.PERSONAL,
        )
        thread = ThreadFactory(
            target_kind=TargetKind.SANCTUM,
            target_trait=None,
            target_sanctum_details=sanctum,
            slot_kind=SanctumSlotKind.PERSONAL_OWN,
        )
        self.assertEqual(compute_anchor_cap(thread), 10)

    def test_sanctum_anchor_cap_level_five(self) -> None:
        """SANCTUM level 5 (max) → cap 50."""
        sanctum = SanctumDetails.objects.create(
            feature_instance=RoomFeatureInstanceFactory(
                feature_kind=RoomFeatureKindFactory(), level=5
            ),
            resonance_type=ResonanceFactory(),
            owner_mode=SanctumOwnerMode.PERSONAL,
        )
        thread = ThreadFactory(
            target_kind=TargetKind.SANCTUM,
            target_trait=None,
            target_sanctum_details=sanctum,
            slot_kind=SanctumSlotKind.PERSONAL_OWN,
        )
        self.assertEqual(compute_anchor_cap(thread), 50)


class CovenantRoleAnchorCapTests(TestCase):
    """COVENANT_ROLE anchor cap: additive formula (issue #517).

    covenant_component (max_covenant_level × ANCHOR_CAP_COVENANT_LEVEL_MULTIPLIER)
    + legend_earned_in_role // ANCHOR_CAP_COVENANT_LEGEND_DIVISOR (personal deeds)
    + days_held_in_role // ANCHOR_CAP_COVENANT_DAYS_DIVISOR (personal tenure).
    Cap is persistent (independent of engagement).
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

    def test_additive_personal_components(self) -> None:
        """Legend-in-role and tenure add cap points on top of the covenant component."""
        from datetime import timedelta

        from django.utils import timezone

        from world.covenants.constants import CovenantType
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            CovenantFactory,
            CovenantRoleFactory,
        )
        from world.scenes.factories import PersonaFactory
        from world.societies.factories import CovenantLegendCreditFactory, LegendEntryFactory

        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        covenant = CovenantFactory(covenant_type=CovenantType.DURANCE, level=3)  # 3x10 = 30
        ccr = CharacterCovenantRoleFactory(
            character_sheet=sheet, covenant=covenant, covenant_role=role
        )
        ccr.joined_at = timezone.now() - timedelta(days=365)  # 365 // 30 = 12
        ccr.save(update_fields=["joined_at"])
        entry = LegendEntryFactory(
            persona=PersonaFactory(character_sheet=sheet), base_value=500, is_active=True
        )  # 500 // 50 = 10
        CovenantLegendCreditFactory(entry=entry, covenant=covenant)

        thread = ThreadFactory(
            owner=sheet,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=role,
            target_trait=None,
        )
        # 30 (covenant) + 10 (legend) + 12 (tenure) = 52
        self.assertEqual(compute_anchor_cap(thread), 52)

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


class SanctumSerializerCapTests(TestCase):
    """ThreadSerializer returns real int anchor_cap and effective_cap for SANCTUM threads."""

    def _make_sanctum_thread(self, level: int) -> "object":
        """Build a SANCTUM thread whose sanctum has the given feature_instance level."""
        sanctum = SanctumDetails.objects.create(
            feature_instance=RoomFeatureInstanceFactory(
                feature_kind=RoomFeatureKindFactory(), level=level
            ),
            resonance_type=ResonanceFactory(),
            owner_mode=SanctumOwnerMode.PERSONAL,
        )
        return ThreadFactory(
            target_kind=TargetKind.SANCTUM,
            target_trait=None,
            target_sanctum_details=sanctum,
            slot_kind=SanctumSlotKind.PERSONAL_OWN,
        )

    def test_anchor_cap_is_integer_for_sanctum_thread(self) -> None:
        """anchor_cap field returns an int (not None) for a SANCTUM thread."""
        from world.magic.serializers import ThreadSerializer

        thread = self._make_sanctum_thread(level=3)
        data = ThreadSerializer(thread).data
        self.assertIsInstance(data["anchor_cap"], int)
        self.assertEqual(data["anchor_cap"], 30)

    def test_effective_cap_is_integer_for_sanctum_thread(self) -> None:
        """effective_cap field returns an int (not None) for a SANCTUM thread."""
        from world.magic.serializers import ThreadSerializer

        thread = self._make_sanctum_thread(level=3)
        data = ThreadSerializer(thread).data
        self.assertIsInstance(data["effective_cap"], int)
        # effective_cap = min(path_cap, anchor_cap); path_cap ≥ 10, anchor_cap = 30
        self.assertEqual(data["effective_cap"], min(data["path_cap"], 30))
