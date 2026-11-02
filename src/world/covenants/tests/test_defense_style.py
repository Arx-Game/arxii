"""How a character defends and which gear fits their vows, both from the combat style (#4975)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import DefenseStyle
from world.covenants.defense import FULL_ARMOR_SHARE_TENTHS, DefenseResolution, defense_style_for
from world.covenants.factories import CovenantRoleFactory, give_combat_style
from world.covenants.style_fit import style_gear_reach
from world.items.constants import GearArchetype


class DefenseStyleForTests(TestCase):
    def test_no_style_has_no_defense_style_and_all_armor_counts(self) -> None:
        character = CharacterSheetFactory().character
        self.assertEqual(
            defense_style_for(character), DefenseResolution(None, FULL_ARMOR_SHARE_TENTHS)
        )

    def test_a_style_sets_the_defense_style_and_armor_share(self) -> None:
        sheet = CharacterSheetFactory()
        give_combat_style(sheet, defense_style=DefenseStyle.BARRIER, armor_share_tenths=4)
        self.assertEqual(
            defense_style_for(sheet.character), DefenseResolution(DefenseStyle.BARRIER, 4)
        )

    def test_a_vow_alone_gives_no_defense(self) -> None:
        """No engaged vow defends for a character: only the combat style does (#4975)."""
        from world.covenants.factories import make_engaged_member

        sheet = CharacterSheetFactory()
        make_engaged_member(character_sheet=sheet)
        sheet.character.covenant_roles.invalidate()
        self.assertEqual(
            defense_style_for(sheet.character), DefenseResolution(None, FULL_ARMOR_SHARE_TENTHS)
        )


class StyleGearReachTests(TestCase):
    def test_no_style_reads_nothing(self) -> None:
        character = CharacterSheetFactory().character
        role = CovenantRoleFactory()
        with self.assertNumQueries(0):
            reach = style_gear_reach(character)
            self.assertFalse(reach.allows(role, GearArchetype.HEAVY_ARMOR))
            self.assertTrue(reach.allows(role, GearArchetype.CLOTHING))

    def test_one_read_serves_every_piece(self) -> None:
        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory()
        other_role = CovenantRoleFactory()
        give_combat_style(sheet, roles=[role], kinds=[GearArchetype.HEAVY_ARMOR])
        with self.assertNumQueries(2):  # the style's gear kinds, and the vows it lists
            reach = style_gear_reach(sheet.character)
        with self.assertNumQueries(0):
            self.assertTrue(reach.allows(role, GearArchetype.HEAVY_ARMOR))
            self.assertFalse(reach.allows(role, GearArchetype.LIGHT_ARMOR))
            self.assertFalse(reach.allows(other_role, GearArchetype.HEAVY_ARMOR))
            self.assertTrue(reach.allows(role, GearArchetype.JEWELRY))
            self.assertTrue(reach.allows(role, ""))
