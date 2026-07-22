"""Unit tests for CmdSphinx — the Sphinx of Black Quartz's telnet verdict (#2640).

Uses the ``_run()`` harness pattern (matches ``test_resonance_command.py`` /
``test_durance_command.py``) — cheap, no Evennia session/connection scaffolding
needed since ``CmdSphinx`` is a plain ``ArxCommand`` calling ``judge_vow`` directly.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from commands.sphinx import CmdSphinx
from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.factories import CovenantRoleFactory, CovenantRoleTechniqueSpecialtyFactory
from world.magic.constants import TechniqueFunction
from world.magic.factories import (
    CharacterTechniqueFactory,
    TechniqueFactory,
    TechniqueFunctionTagFactory,
)


def _run(cmd_cls, caller, args=""):
    """Build a command instance and call func(); return the list of msg strings."""
    cmd = cmd_cls()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"{cmd_cls.key} {args}".strip()
    caller.msg = MagicMock()
    cmd.func()
    return [str(c.args[0]) for c in caller.msg.call_args_list if c.args]


class SphinxNoIdentityTests(TestCase):
    def test_no_character_sheet_shows_error(self) -> None:
        bare_char = CharacterFactory(db_key="SphinxNoSheetChar")
        msgs = _run(CmdSphinx, bare_char, "Vanguard")
        combined = "\n".join(msgs)
        self.assertIn("no active character", combined.lower())


class SphinxUsageTests(TestCase):
    def setUp(self) -> None:
        self.char = CharacterFactory(db_key="SphinxUsageChar")
        self.sheet = CharacterSheetFactory(character=self.char)

    def test_bare_sphinx_shows_usage(self) -> None:
        msgs = _run(CmdSphinx, self.char, "")
        combined = "\n".join(msgs)
        self.assertIn("usage", combined.lower())

    def test_unknown_vow_name(self) -> None:
        msgs = _run(CmdSphinx, self.char, "Nonexistent Vow")
        combined = "\n".join(msgs)
        self.assertIn("does not know", combined.lower())


class SphinxVerdictRenderTests(TestCase):
    def setUp(self) -> None:
        self.char = CharacterFactory(db_key="SphinxVerdictChar")
        self.sheet = CharacterSheetFactory(character=self.char)

    def test_full_coverage_renders_takes(self) -> None:
        role = CovenantRoleFactory(name="Sundering Vow")
        CovenantRoleTechniqueSpecialtyFactory(covenant_role=role, function=TechniqueFunction.WEAKEN)
        technique = TechniqueFactory(name="Sundering Blow")
        TechniqueFunctionTagFactory(technique=technique, function=TechniqueFunction.WEAKEN)
        CharacterTechniqueFactory(character=self.sheet, technique=technique)

        msgs = _run(CmdSphinx, self.char, "Sundering Vow")
        combined = "\n".join(msgs)
        self.assertIn("The vow will take.", combined)
        self.assertIn("Sundering Blow", combined)

    def test_partial_coverage_renders_dormant(self) -> None:
        role = CovenantRoleFactory(name="Half Answered Vow")
        CovenantRoleTechniqueSpecialtyFactory(covenant_role=role, function=TechniqueFunction.WEAKEN)
        CovenantRoleTechniqueSpecialtyFactory(covenant_role=role, function=TechniqueFunction.CHARM)
        technique = TechniqueFactory()
        TechniqueFunctionTagFactory(technique=technique, function=TechniqueFunction.WEAKEN)
        CharacterTechniqueFactory(character=self.sheet, technique=technique)

        msgs = _run(CmdSphinx, self.char, "Half Answered Vow")
        combined = "\n".join(msgs)
        self.assertIn("would lie dormant in places", combined)

    def test_no_coverage_renders_not_yet_with_shopping_list(self) -> None:
        role = CovenantRoleFactory(name="Unready Vow")
        CovenantRoleTechniqueSpecialtyFactory(
            covenant_role=role, function=TechniqueFunction.BARRIER
        )
        learnable = TechniqueFactory(name="Ward of Black Quartz")
        TechniqueFunctionTagFactory(technique=learnable, function=TechniqueFunction.BARRIER)

        msgs = _run(CmdSphinx, self.char, "Unready Vow")
        combined = "\n".join(msgs)
        self.assertIn("The vow will not take", combined)
        self.assertIn("Ward of Black Quartz", combined)
