"""Integration: use-based COVENANT_ROLE anchor cap distinguishes holders (issue #517).

A long-held, legend-rich holder out-caps a briefly-held, low-legend holder of the
SAME role at the SAME covenant level — isolating the personal component from the
shared covenant component.
"""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import CovenantType
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
)
from world.magic.constants import TargetKind
from world.magic.factories import ThreadFactory
from world.magic.services import compute_anchor_cap
from world.scenes.factories import PersonaFactory
from world.societies.factories import CovenantLegendCreditFactory, LegendEntryFactory


class UseBasedCovenantCapTests(TestCase):
    def test_veteran_out_caps_newcomer_same_role_same_covenant(self) -> None:
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        covenant = CovenantFactory(covenant_type=CovenantType.DURANCE, level=3)  # 30 for both

        # Veteran: held 365 days + 500 legend credited to the covenant
        vet = CharacterSheetFactory()
        vet_ccr = CharacterCovenantRoleFactory(
            character_sheet=vet, covenant=covenant, covenant_role=role
        )
        vet_ccr.joined_at = timezone.now() - timedelta(days=365)  # 365 // 30 = 12
        vet_ccr.save(update_fields=["joined_at"])
        vet_entry = LegendEntryFactory(
            persona=PersonaFactory(character_sheet=vet), base_value=500, is_active=True
        )  # 500 // 50 = 10
        CovenantLegendCreditFactory(entry=vet_entry, covenant=covenant)
        vet_thread = ThreadFactory(
            owner=vet,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=role,
            target_trait=None,
        )

        # Newcomer: just joined, no legend
        new = CharacterSheetFactory()
        CharacterCovenantRoleFactory(character_sheet=new, covenant=covenant, covenant_role=role)
        new_thread = ThreadFactory(
            owner=new,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=role,
            target_trait=None,
        )

        vet_cap = compute_anchor_cap(vet_thread)
        new_cap = compute_anchor_cap(new_thread)

        self.assertEqual(new_cap, 30)  # covenant component only
        self.assertEqual(vet_cap, 52)  # 30 + 10 + 12
        self.assertGreater(vet_cap, new_cap)
