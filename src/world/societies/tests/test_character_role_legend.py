"""Unit tests for get_character_role_legend (issue #517)."""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import CovenantType
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
)
from world.scenes.factories import PersonaFactory
from world.societies.factories import (
    CovenantLegendCreditFactory,
    LegendEntryFactory,
    LegendSpreadFactory,
)
from world.societies.services import get_character_role_legend


class GetCharacterRoleLegendTests(TestCase):
    def _hold(self, sheet, role, covenant):
        return CharacterCovenantRoleFactory(
            character_sheet=sheet, covenant=covenant, covenant_role=role
        )

    def test_zero_when_role_never_held(self) -> None:
        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory()
        self.assertEqual(get_character_role_legend(character_sheet=sheet, role=role), 0)

    def test_sums_base_value_credited_to_held_covenant(self) -> None:
        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        covenant = CovenantFactory(covenant_type=CovenantType.DURANCE)
        self._hold(sheet, role, covenant)
        persona = PersonaFactory(character_sheet=sheet)
        entry = LegendEntryFactory(persona=persona, base_value=80, is_active=True)
        CovenantLegendCreditFactory(entry=entry, covenant=covenant)
        self.assertEqual(get_character_role_legend(character_sheet=sheet, role=role), 80)

    def test_includes_spreads(self) -> None:
        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        covenant = CovenantFactory(covenant_type=CovenantType.DURANCE)
        self._hold(sheet, role, covenant)
        persona = PersonaFactory(character_sheet=sheet)
        entry = LegendEntryFactory(persona=persona, base_value=80, is_active=True)
        CovenantLegendCreditFactory(entry=entry, covenant=covenant)
        LegendSpreadFactory(legend_entry=entry, value_added=15)
        LegendSpreadFactory(legend_entry=entry, value_added=5)
        self.assertEqual(get_character_role_legend(character_sheet=sheet, role=role), 100)

    def test_excludes_inactive_entries(self) -> None:
        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        covenant = CovenantFactory(covenant_type=CovenantType.DURANCE)
        self._hold(sheet, role, covenant)
        persona = PersonaFactory(character_sheet=sheet)
        entry = LegendEntryFactory(persona=persona, base_value=80, is_active=False)
        CovenantLegendCreditFactory(entry=entry, covenant=covenant)
        self.assertEqual(get_character_role_legend(character_sheet=sheet, role=role), 0)

    def test_excludes_other_characters_legend(self) -> None:
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        covenant = CovenantFactory(covenant_type=CovenantType.DURANCE)
        me = CharacterSheetFactory()
        other = CharacterSheetFactory()
        self._hold(me, role, covenant)
        self._hold(other, role, covenant)
        other_entry = LegendEntryFactory(
            persona=PersonaFactory(character_sheet=other), base_value=500, is_active=True
        )
        CovenantLegendCreditFactory(entry=other_entry, covenant=covenant)
        self.assertEqual(get_character_role_legend(character_sheet=me, role=role), 0)

    def test_counts_entry_once_even_if_credited_to_two_held_covenants(self) -> None:
        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        cov_a = CovenantFactory(covenant_type=CovenantType.DURANCE)
        cov_b = CovenantFactory(covenant_type=CovenantType.DURANCE)
        self._hold(sheet, role, cov_a)
        self._hold(sheet, role, cov_b)
        entry = LegendEntryFactory(
            persona=PersonaFactory(character_sheet=sheet), base_value=90, is_active=True
        )
        CovenantLegendCreditFactory(entry=entry, covenant=cov_a)
        CovenantLegendCreditFactory(entry=entry, covenant=cov_b)
        self.assertEqual(get_character_role_legend(character_sheet=sheet, role=role), 90)
