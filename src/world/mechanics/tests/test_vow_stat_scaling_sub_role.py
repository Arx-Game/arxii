"""Vow stat scaling counts the anchor role for a holder graduated to a sub-role (#4783).

Rows and COVENANT_ROLE threads key on the ANCHOR (parent) role; the engaged role
the handler returns is the resolved sub-role (ADR-0055). A row authored on the
anchor must still apply to the graduated holder, and a row on the sub-role itself
reads its thread level from the anchor.
"""

from django.test import TestCase

from world.covenants.constants import CovenantType
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantRoleFactory,
    SubroleCovenantRoleFactory,
)
from world.covenants.models import VowStatScaling
from world.covenants.services import set_engaged_membership
from world.magic.constants import TargetKind
from world.magic.factories import ResonanceFactory, ThreadFactory
from world.mechanics.factories import ModifierTargetFactory
from world.mechanics.services import vow_stat_scaling_bonus


class VowStatScalingSubRoleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.anchor = CovenantRoleFactory(covenant_type=CovenantType.DURANCE, shield_weight=1)
        cls.resonance = ResonanceFactory()
        cls.sub_role = SubroleCovenantRoleFactory(
            parent_role=cls.anchor,
            resonance=cls.resonance,
            unlock_thread_level=3,
        )
        cls.target = ModifierTargetFactory()

    def _engaged_holder(self, *, thread_level: int):
        membership = CharacterCovenantRoleFactory(covenant_role=self.anchor)
        sheet = membership.character_sheet
        ThreadFactory(
            owner=sheet,
            resonance=self.resonance,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=self.anchor,
            target_trait=None,
            level=thread_level,
        )
        set_engaged_membership(membership=membership)
        return sheet

    def test_row_on_anchor_applies_to_graduated_sub_role_holder(self):
        VowStatScaling.objects.create(
            covenant_role=self.anchor, modifier_target=self.target, bonus_per_level=3
        )
        # 30 stored shows 3, the sub-role's unlock level, so the holder graduates.
        sheet = self._engaged_holder(thread_level=30)
        self.assertEqual(
            sheet.character.covenant_roles.currently_engaged_primary_roles(), [self.sub_role]
        )
        self.assertEqual(vow_stat_scaling_bonus(sheet, self.target), 90)

    def test_rows_on_anchor_and_sub_role_sum(self):
        VowStatScaling.objects.create(
            covenant_role=self.anchor, modifier_target=self.target, bonus_per_level=3
        )
        VowStatScaling.objects.create(
            covenant_role=self.sub_role, modifier_target=self.target, bonus_per_level=1
        )
        sheet = self._engaged_holder(thread_level=30)
        # (3 + 1) per level, both read from the anchor thread at stored level 30.
        self.assertEqual(vow_stat_scaling_bonus(sheet, self.target), 120)

    def test_anchor_holder_unchanged(self):
        VowStatScaling.objects.create(
            covenant_role=self.anchor, modifier_target=self.target, bonus_per_level=3
        )
        VowStatScaling.objects.create(
            covenant_role=self.sub_role, modifier_target=self.target, bonus_per_level=1
        )
        # Below the unlock level: the holder stays on the anchor, the sub-role row is ignored.
        sheet = self._engaged_holder(thread_level=20)
        self.assertEqual(
            sheet.character.covenant_roles.currently_engaged_primary_roles(), [self.anchor]
        )
        self.assertEqual(vow_stat_scaling_bonus(sheet, self.target), 60)
