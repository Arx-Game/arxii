"""Wiring-proof: VowStatScaling flows into ``equipment_walk_total`` (#2533).

``vow_stat_scaling_bonus`` is unit-tested directly in
``world.covenants.tests.test_vow_scaling``. This test proves the second half of the
wiring contract: an authored ``VowStatScaling`` row for an engaged role, scaled by
the character's COVENANT_ROLE thread level, is actually folded into the aggregate
``equipment_walk_total`` pipeline (Spec D §5.5) — not just returned by the narrow
service function in isolation.
"""

from __future__ import annotations

from django.test import TestCase


class VowStatScalingEquipmentWalkTotalTests(TestCase):
    """A VowStatScaling row for an engaged role's thread contributes via equipment_walk_total."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import CharacterFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.covenants.constants import CovenantType
        from world.covenants.factories import CovenantRoleFactory, make_engaged_member
        from world.covenants.models import VowStatScaling
        from world.magic.constants import TargetKind
        from world.magic.factories import ResonanceFactory
        from world.magic.models import Thread
        from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory

        cls.bonus_per_level = 4
        cls.thread_level = 7

        cls.character = CharacterFactory(db_key="VowStatScalingWiringChar")
        cls.sheet = CharacterSheetFactory(character=cls.character, primary_persona=False)

        # Category name must be an exact EQUIPMENT_RELEVANT_CATEGORIES member
        # (mechanics/constants.py checks target.category.name == "stat", not a prefix).
        cls.category = ModifierCategoryFactory(name="stat")
        cls.target = ModifierTargetFactory(name="vow_wiring_target", category=cls.category)

        cls.role = CovenantRoleFactory(
            covenant_type=CovenantType.DURANCE, sword_weight=1, crown_weight=0
        )
        cls.membership = make_engaged_member(character_sheet=cls.sheet, covenant_role=cls.role)

        VowStatScaling.objects.create(
            covenant_role=cls.role,
            modifier_target=cls.target,
            bonus_per_level=cls.bonus_per_level,
        )

        cls.resonance = ResonanceFactory()
        Thread.objects.create(
            owner=cls.sheet,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=cls.role,
            resonance=cls.resonance,
            level=cls.thread_level,
        )

    def test_vow_stat_scaling_bonus_scales_by_thread_level(self) -> None:
        """vow_stat_scaling_bonus returns thread_level * bonus_per_level."""
        from world.mechanics.services import vow_stat_scaling_bonus

        expected = self.thread_level * self.bonus_per_level
        self.assertEqual(vow_stat_scaling_bonus(self.sheet, self.target), expected)

    def test_equipment_walk_total_includes_vow_stat_scaling(self) -> None:
        """equipment_walk_total folds in the vow-scaled bonus for an equipment-relevant target."""
        from world.mechanics.services import equipment_walk_total, vow_stat_scaling_bonus

        expected_vow_component = self.thread_level * self.bonus_per_level
        self.assertEqual(expected_vow_component, vow_stat_scaling_bonus(self.sheet, self.target))

        total = equipment_walk_total(self.sheet, self.target)
        self.assertGreaterEqual(total, expected_vow_component)

        # Isolate the vow component: everything else in the walk is 0 for this
        # otherwise-bare fixture (no equipped items, no facets, no mantle/motif
        # threads, no covenant level bonus row), so the full total must equal it.
        self.assertEqual(total, expected_vow_component)
