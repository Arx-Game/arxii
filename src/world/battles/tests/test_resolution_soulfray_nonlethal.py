"""Soulfray can kill only in combat encounters (#4098 fix round 2).

A battle is not a ``CombatEncounter`` — ``resolve_battle_technique`` must pass
``lethal=False`` to ``use_technique`` explicitly so a ``character_loss``
Soulfray consequence can never be selected there, same as a scene cast
(``world.scenes.tests.test_cast_soulfray_nonlethal``).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.factories import ActionTemplateFactory
from world.battles.constants import BattleActionKind, BattleSideRole
from world.battles.resolution import resolve_battle_technique
from world.battles.services import (
    add_side,
    begin_battle_round,
    create_battle,
    declare_battle_action,
    enlist_participant,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import CharacterAnimaFactory, CharacterTechniqueFactory, TechniqueFactory

# use_technique is imported lazily inside resolve_battle_technique via
# `from world.magic.services import use_technique` — patch the re-export point
# (repo convention, see world/combat/tests/test_resolve_combat_technique_fury.py).
_USE_TECHNIQUE_PATCH = "world.magic.services.use_technique"


class BattleTechniqueIsNeverLethalTests(TestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.technique = TechniqueFactory(
            action_template=ActionTemplateFactory(), damage_profile=False
        )
        CharacterTechniqueFactory(character=self.sheet, technique=self.technique)
        CharacterAnimaFactory(character=self.sheet, current=20, maximum=30)

    def test_battle_technique_passes_lethal_false_to_use_technique(self) -> None:
        battle = create_battle(name="Nonlethal Soulfray Unit Test Battle")
        side = add_side(battle=battle, role=BattleSideRole.ATTACKER)
        participant = enlist_participant(battle=battle, character_sheet=self.sheet, side=side)
        begin_battle_round(battle=battle)
        declaration = declare_battle_action(
            participant=participant,
            action_kind=BattleActionKind.SUPPORT,
            technique=self.technique,
        )

        mock_result = MagicMock(confirmed=False, resolution_result=None)
        with patch(_USE_TECHNIQUE_PATCH, return_value=mock_result) as mock_use:
            resolve_battle_technique(declaration=declaration)

        mock_use.assert_called_once()
        self.assertFalse(mock_use.call_args.kwargs["lethal"])
