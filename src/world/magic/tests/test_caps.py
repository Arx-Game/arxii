"""Tests for cap helpers: compute_anchor_cap, compute_path_cap, compute_effective_cap.

Spec A §2.4. TDD: written before the implementation.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
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
