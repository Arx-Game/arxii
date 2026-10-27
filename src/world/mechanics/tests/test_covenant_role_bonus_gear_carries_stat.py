"""The covenant role bonus blends against gear that carries the stat (#4757).

A ring or cloak carries no weapon damage and no armor soak, so it must not add the
role bonus again. Only the weapon (for weapon_damage) or the armor (for armor_soak)
contributes.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.factories import make_engaged_member
from world.items.constants import GearArchetype
from world.items.factories import (
    EquippedItemFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
)
from world.mechanics.factories import ModifierTargetFactory
from world.mechanics.services import covenant_role_bonus

ROLE_BONUS = 10


class CovenantRoleBonusGearCarriesStatTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory(db_key="GearCarriesStatChar")
        cls.sheet = CharacterSheetFactory(character=cls.character, primary_persona=False)
        make_engaged_member(character_sheet=cls.sheet)
        cls.weapon_target = ModifierTargetFactory(name="weapon_damage")
        cls.soak_target = ModifierTargetFactory(name="armor_soak")

    def setUp(self) -> None:
        self.character.covenant_roles.invalidate()
        self.character.equipped_items.invalidate()

    def _equip(self, *, weapon_damage: int = 0, armor_soak: int = 0, archetype: str) -> None:
        template = ItemTemplateFactory(
            gear_archetype=archetype,
            base_weapon_damage=weapon_damage,
            base_armor_soak=armor_soak,
        )
        EquippedItemFactory(
            character=self.character.sheet_data,
            item_instance=ItemInstanceFactory(template=template),
        )
        self.character.equipped_items.invalidate()

    def _bonus(self, target) -> int:
        # Isolate the per-item walk: a fixed role bonus, and no gear stat to blend against.
        with (
            patch("world.mechanics.services.role_base_bonus_for_target", return_value=ROLE_BONUS),
            patch("world.mechanics.services.item_mundane_stat_for_target", return_value=0),
        ):
            return covenant_role_bonus(self.sheet, target)

    def test_ring_adds_no_weapon_damage_role_bonus(self) -> None:
        self._equip(weapon_damage=5, archetype=GearArchetype.MELEE_ONE_HAND)
        self._equip(archetype=GearArchetype.ROBE)  # a ring: no weapon damage

        self.assertEqual(self._bonus(self.weapon_target), ROLE_BONUS)

    def test_ring_adds_no_armor_soak_role_bonus(self) -> None:
        self._equip(armor_soak=3, archetype=GearArchetype.HEAVY_ARMOR)
        self._equip(archetype=GearArchetype.ROBE)  # a ring: no armor soak

        self.assertEqual(self._bonus(self.soak_target), ROLE_BONUS)

    def test_no_weapon_worn_gives_no_weapon_damage_role_bonus(self) -> None:
        self._equip(archetype=GearArchetype.ROBE)

        self.assertEqual(self._bonus(self.weapon_target), 0)
