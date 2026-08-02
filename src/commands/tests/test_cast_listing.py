"""Bare ``cast`` is the telnet cast list (#2898).

Telnet had no way to find out what a technique does. ``sheet/magic`` printed name
and level; bare ``cast`` raised a usage error. This is the telnet face of the web
castable-techniques list — both read ``castable_techniques_for_sheet``.
"""

from __future__ import annotations

from django.test import TestCase

from actions.factories import ActionTemplateFactory
from commands.combat import CmdDeclareTechnique
from world.character_sheets.factories import CharacterFactory, CharacterSheetFactory
from world.conditions.factories import ConditionTemplateFactory
from world.magic.factories import (
    BinaryEffectTypeFactory,
    CharacterTechniqueFactory,
    TechniqueAppliedConditionFactory,
    TechniqueFactory,
)
from world.magic.models.techniques import ConditionTargetKind


class _RecordingCmd(CmdDeclareTechnique):
    """CmdDeclareTechnique with ``msg`` captured instead of sent to a session."""

    def __init__(self, caller, args: str = "") -> None:
        super().__init__()
        self.caller = caller
        self.args = args
        self.sent: list[str] = []

    def msg(self, text="", **kwargs) -> None:
        self.sent.append(str(text))


class CastListingTests(TestCase):
    def setUp(self) -> None:
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)

    def _technique(self, name: str):
        # An action_template is what makes a technique castable standalone.
        technique = TechniqueFactory(
            name=name,
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            anima_cost=5,
            action_template=ActionTemplateFactory(),
        )
        TechniqueAppliedConditionFactory(
            technique=technique,
            condition=ConditionTemplateFactory(name="Guarded"),
            target_kind=ConditionTargetKind.ALLY,
        )
        CharacterTechniqueFactory(character=self.sheet, technique=technique)
        return technique

    def test_bare_cast_lists_techniques_with_what_they_do(self) -> None:
        technique = self._technique("Ward of Ash")

        cmd = _RecordingCmd(self.character)
        cmd.func()
        text = "\n".join(cmd.sent)

        self.assertIn("Ward of Ash", text)
        self.assertIn("Cast on an ally", text)
        self.assertIn("Costs 5 anima.", text)
        self.assertIn("Applies Guarded.", text)
        self.assertIn(technique.description, text)

    def test_bare_cast_with_no_techniques_says_so(self) -> None:
        cmd = _RecordingCmd(self.character)
        cmd.func()

        self.assertEqual(cmd.sent, ["You know no techniques you can cast."])

    def test_listing_does_not_scale_queries_with_technique_count(self) -> None:
        """The payload tables prefetch onto the cached_property names the summary
        reads, so N techniques cost a fixed handful of queries, not 4N."""
        for name in ("Ward of Ash", "Ember Lash", "Cinder Step", "Ash Veil"):
            self._technique(name)

        cmd = _RecordingCmd(self.character)
        with self.assertNumQueries(5):
            lines = cmd._castable_listing()

        self.assertIn("Ash Veil", "\n".join(lines))
