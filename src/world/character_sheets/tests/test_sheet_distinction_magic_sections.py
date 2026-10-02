"""Tests for the telnet ``sheet/distinction`` and ``sheet/magic`` sections (#1446).

Telnet parity for the web Distinctions and Magic (spellbook) tabs — both faces read the
same ``_build_distinctions`` / ``_build_magic`` builders, so they can't drift.
"""

from unittest.mock import MagicMock

from django.test import TestCase

from commands.account.sheet_sections import SHEET_SECTIONS
from world.character_sheets.factories import CharacterFactory, CharacterSheetFactory
from world.distinctions.factories import CharacterDistinctionFactory, DistinctionFactory
from world.magic.factories import (
    CharacterGiftFactory,
    CharacterResonanceFactory,
    GiftFactory,
    ResonanceFactory,
)
from world.secrets.factories import SecretFactory


def _command_for(character) -> MagicMock:
    command = MagicMock()
    command.caller.puppet = character
    command.args = ""
    return command


class SheetDistinctionSectionTests(TestCase):
    def setUp(self) -> None:
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)

    def test_registered_with_aliases(self) -> None:
        self.assertIn("distinction", SHEET_SECTIONS)
        self.assertIn("distinctions", SHEET_SECTIONS)
        self.assertIn("magic", SHEET_SECTIONS)

    def test_lists_distinctions_with_rank_and_secret_marker(self) -> None:
        public = CharacterDistinctionFactory(
            character=self.sheet,
            distinction=DistinctionFactory(name="Silver Tongue"),
            rank=2,
        )
        hidden = CharacterDistinctionFactory(
            character=self.sheet,
            distinction=DistinctionFactory(name="Blood Debt"),
            rank=1,
            secret=SecretFactory(),
        )

        lines = SHEET_SECTIONS["distinction"](_command_for(self.character))
        text = "\n".join(lines)

        self.assertIn(public.distinction.name, text)
        self.assertIn("rank 2", text)
        self.assertIn(hidden.distinction.name, text)  # owner sees gated entries
        self.assertIn("(secret)", text)

    def test_empty_state(self) -> None:
        lines = SHEET_SECTIONS["distinction"](_command_for(self.character))
        self.assertEqual(lines, ["You have no distinctions."])


class SheetMagicSectionTests(TestCase):
    def setUp(self) -> None:
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)

    def test_lists_gifts(self) -> None:
        gift_row = CharacterGiftFactory(
            character=self.sheet,
            gift=GiftFactory(name="Emberweaving"),
        )

        lines = SHEET_SECTIONS["magic"](_command_for(self.character))
        text = "\n".join(lines)

        self.assertIn(gift_row.gift.name, text)

    def test_empty_state(self) -> None:
        lines = SHEET_SECTIONS["magic"](_command_for(self.character))
        self.assertEqual(lines, ["Nothing is known of your magic."])

    def test_lists_what_each_technique_does(self) -> None:
        """#2898 — the section used to print name and level and nothing else, so a
        player could read their own spellbook without learning what any of it did."""
        from world.conditions.factories import ConditionTemplateFactory
        from world.magic.factories import (
            BinaryEffectTypeFactory,
            CharacterTechniqueFactory,
            TechniqueAppliedConditionFactory,
            TechniqueFactory,
        )
        from world.magic.models.techniques import ConditionTargetKind

        gift = GiftFactory(name="Emberweaving")
        CharacterGiftFactory(character=self.sheet, gift=gift)
        technique = TechniqueFactory(
            name="Ward of Ash",
            gift=gift,
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            anima_cost=5,
        )
        TechniqueAppliedConditionFactory(
            technique=technique,
            condition=ConditionTemplateFactory(name="Guarded"),
            target_kind=ConditionTargetKind.ALLY,
        )
        CharacterTechniqueFactory(character=self.sheet, technique=technique)

        lines = SHEET_SECTIONS["magic"](_command_for(self.character))
        text = "\n".join(lines)

        self.assertIn("Ward of Ash", text)
        self.assertIn("Cast on an ally", text)
        self.assertIn("Costs 5 anima.", text)
        self.assertIn("Applies Guarded.", text)

    def test_shows_catalog_name_price_and_next_flourish_without_a_locked_form(self) -> None:
        """#4099 fix round 1: the next flourish shows even with no locked form.

        The "Not yet yours:" header used to print only when a locked variant form
        existed, so a technique with no locked form but an eligible next flourish
        showed nothing — a silent gap against demo Screen 4 and the spec.
        """
        from world.magic.constants import TargetKind
        from world.magic.factories import (
            CharacterTechniqueFactory,
            PriceFactory,
            SignatureMotifBonusFactory,
            TechniqueFactory,
        )
        from world.magic.models import Thread

        gift = GiftFactory(name="Emberweaving")
        CharacterGiftFactory(character=self.sheet, gift=gift)
        resonance = ResonanceFactory()
        technique = TechniqueFactory(gift=gift, name="Scorch Lash", level=1)
        CharacterTechniqueFactory(
            character=self.sheet,
            technique=technique,
            custom_name="Winterbite",
            price=PriceFactory(name="Frost on the skin", power_bonus=4),
        )
        Thread.objects.create(
            owner=self.sheet,
            resonance=resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_technique=technique,
            level=1,
        )
        SignatureMotifBonusFactory(
            name="Rime walks with you", required_resonance=resonance, min_crossing_level=3
        )

        lines = SHEET_SECTIONS["magic"](_command_for(self.character))
        text = "\n".join(lines)

        self.assertIn("Winterbite (Scorch Lash, level 1)", text)
        self.assertIn("Price: Frost on the skin", text)
        self.assertIn("Not yet yours:", text)
        self.assertIn("Rime walks with you, at thread level 3", text)

    def test_price_line_shows_what_the_price_costs(self) -> None:
        """#4099: the telnet price line carries the price's real cost, like the web."""
        from world.conditions.factories import ConditionTemplateFactory
        from world.items.factories import ItemTemplateFactory
        from world.magic.factories import (
            CharacterTechniqueFactory,
            PriceFactory,
            TechniqueFactory,
        )
        from world.magic.models import PriceComponentRequirement

        gift = GiftFactory(name="Bloodwork")
        CharacterGiftFactory(character=self.sheet, gift=gift)
        price = PriceFactory(
            name="Blood on the needle",
            inflicted_condition=ConditionTemplateFactory(name="Lightheaded"),
        )
        PriceComponentRequirement.objects.create(
            restriction=price, item_template=ItemTemplateFactory(name="Silver needle"), quantity=2
        )
        CharacterTechniqueFactory(
            character=self.sheet,
            technique=TechniqueFactory(gift=gift, name="Red Thread", level=1),
            price=price,
        )

        text = "\n".join(SHEET_SECTIONS["magic"](_command_for(self.character)))

        self.assertIn("Price: Blood on the needle", text)
        self.assertIn("Consumes: 2x Silver needle", text)
        self.assertIn("Inflicts: Lightheaded", text)

    def test_lists_resonance_balances(self) -> None:
        """#2032 — claimed resonances render with balance + lifetime earned."""
        CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=ResonanceFactory(name="Ember"),
            balance=15,
            lifetime_earned=40,
        )

        lines = SHEET_SECTIONS["magic"](_command_for(self.character))
        text = "\n".join(lines)

        self.assertIn("Ember", text)
        self.assertIn("15", text)
        self.assertIn("40", text)
