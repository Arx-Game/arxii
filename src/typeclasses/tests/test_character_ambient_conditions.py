"""Unit tests for the three new Character DSL-backing methods (#2471 v2)."""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.factories import DistinctionFactory
from world.distinctions.models import CharacterDistinction
from world.magic.factories import CharacterResonanceFactory, ResonanceFactory
from world.secrets.factories import SecretFactory
from world.societies.constants import FameTier
from world.societies.factories import SocietyFactory


def _character_with_sheet():
    character = CharacterFactory()
    CharacterSheetFactory(character=character)
    return character


class HasResonanceAtLeastTests(TestCase):
    def test_true_when_lifetime_meets_minimum(self) -> None:
        character = _character_with_sheet()
        resonance = ResonanceFactory(name="Abyssal")
        CharacterResonanceFactory(
            character_sheet=character.character_sheet, resonance=resonance, lifetime_earned=100
        )
        self.assertTrue(character.has_resonance_at_least({"resonance": "Abyssal", "minimum": 50}))

    def test_false_when_below_minimum(self) -> None:
        character = _character_with_sheet()
        resonance = ResonanceFactory(name="Abyssal")
        CharacterResonanceFactory(
            character_sheet=character.character_sheet, resonance=resonance, lifetime_earned=10
        )
        self.assertFalse(character.has_resonance_at_least({"resonance": "Abyssal", "minimum": 50}))

    def test_false_when_resonance_unknown(self) -> None:
        character = _character_with_sheet()
        self.assertFalse(
            character.has_resonance_at_least({"resonance": "Nonexistent", "minimum": 1})
        )


class HasPublicDistinctionTests(TestCase):
    def test_true_for_public_distinction(self) -> None:
        character = _character_with_sheet()
        distinction = DistinctionFactory(slug="blooded-duelist")
        CharacterDistinction.objects.create(character=character, distinction=distinction)
        self.assertTrue(character.has_public_distinction("blooded-duelist"))

    def test_false_for_secret_relocated_distinction(self) -> None:
        character = _character_with_sheet()
        distinction = DistinctionFactory(slug="blooded-duelist")
        secret = SecretFactory()
        CharacterDistinction.objects.create(
            character=character, distinction=distinction, secret=secret
        )
        self.assertFalse(character.has_public_distinction("blooded-duelist"))

    def test_false_when_not_held(self) -> None:
        character = _character_with_sheet()
        self.assertFalse(character.has_public_distinction("nonexistent-slug"))


class FameTierAtLeastTests(TestCase):
    def test_true_when_tier_meets_minimum(self) -> None:
        character = _character_with_sheet()
        persona = character.character_sheet.primary_persona
        persona.fame_tier = FameTier.CELEBRITY
        persona.save(update_fields=["fame_tier"])
        self.assertTrue(
            character.fame_tier_at_least(
                {"min_tier": FameTier.CELEBRITY, "perceiving_society": None}
            )
        )

    def test_false_when_below_minimum(self) -> None:
        character = _character_with_sheet()
        persona = character.character_sheet.primary_persona
        persona.fame_tier = FameTier.NORMAL
        persona.save(update_fields=["fame_tier"])
        self.assertFalse(
            character.fame_tier_at_least(
                {"min_tier": FameTier.CELEBRITY, "perceiving_society": None}
            )
        )

    def test_insular_society_perceives_less(self) -> None:
        character = _character_with_sheet()
        persona = character.character_sheet.primary_persona
        persona.fame_tier = FameTier.CELEBRITY
        persona.save(update_fields=["fame_tier"])
        insular = SocietyFactory(fame_perception_offset=-2)
        # CELEBRITY (index 2) - 2 = NORMAL < CELEBRITY threshold -> False.
        self.assertFalse(
            character.fame_tier_at_least(
                {"min_tier": FameTier.CELEBRITY, "perceiving_society": insular.name}
            )
        )


class HasLegendDeedsTests(TestCase):
    def test_false_when_no_deeds(self) -> None:
        character = _character_with_sheet()
        self.assertFalse(character.has_legend_deeds())

    def test_true_when_common_knowledge_deed_exists(self) -> None:
        from world.societies.factories import (
            LegendEntryFactory,
            LegendSpreadFactory,
        )

        character = _character_with_sheet()
        persona = character.character_sheet.primary_persona
        deed = LegendEntryFactory(persona=persona, base_value=10, is_active=True)
        LegendSpreadFactory(legend_entry=deed, value_added=40)
        self.assertTrue(character.has_legend_deeds())

    def test_false_when_only_non_common_knowledge_deeds(self) -> None:
        from world.societies.factories import LegendEntryFactory

        character = _character_with_sheet()
        persona = character.character_sheet.primary_persona
        LegendEntryFactory(persona=persona, base_value=10, is_active=True)
        self.assertFalse(character.has_legend_deeds())

    def test_false_when_only_secret_linked_deeds(self) -> None:
        from world.secrets.factories import SecretFactory
        from world.societies.factories import (
            LegendEntryFactory,
            LegendSpreadFactory,
        )

        character = _character_with_sheet()
        persona = character.character_sheet.primary_persona
        deed = LegendEntryFactory(persona=persona, base_value=10, is_active=True)
        LegendSpreadFactory(legend_entry=deed, value_added=40)
        SecretFactory(legend_deed=deed)
        self.assertFalse(character.has_legend_deeds())

    def test_false_when_no_sheet(self) -> None:
        from evennia_extensions.factories import CharacterFactory

        character = CharacterFactory()
        self.assertFalse(character.has_legend_deeds())
