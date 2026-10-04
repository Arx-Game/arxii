"""Regard rules matched against characters."""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.factories import CreatureTemplateFactory
from world.mechanics.factories import PropertyFactory
from world.scenes.factories import PersonaFactory
from world.societies.factories import (
    LegendEntryFactory,
    LegendSpreadFactory,
    PhilosophicalArchetypeFactory,
)
from world.species.factories import SpeciesFactory
from world.standoffs.constants import DriveStrength
from world.standoffs.factories import (
    CreatureDriveFactory,
    RegardRuleFactory,
    StandoffGroupFactory,
)
from world.standoffs.services.regard import (
    band_shift_toward,
    drive_strength_toward,
    regard_matches,
)


class RegardTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = CreatureTemplateFactory()
        cls.group = StandoffGroupFactory(creature_template=cls.template)
        cls.cinderi = SpeciesFactory()
        cls.other = SpeciesFactory()
        cls.cinderi_sheet = CharacterSheetFactory(character=CharacterFactory(), species=cls.cinderi)
        cls.other_sheet = CharacterSheetFactory(character=CharacterFactory(), species=cls.other)

    def test_species_rule_matches_only_that_species(self) -> None:
        rule = RegardRuleFactory(
            creature_template=self.template,
            rule={"leaf": "has_species", "params": {"species_id": self.cinderi.pk}},
        )
        matches = regard_matches(self.group, self.cinderi_sheet)
        self.assertEqual([m.rule for m in matches], [rule])
        self.assertTrue(matches[0].reasons)
        self.assertEqual(regard_matches(self.group, self.other_sheet), [])

    def test_deed_archetype_needs_common_knowledge_deed(self) -> None:
        archetype = PhilosophicalArchetypeFactory()
        RegardRuleFactory(creature_template=self.template, rule={}, deed_archetype=archetype)
        entry = LegendEntryFactory(persona=self.cinderi_sheet.primary_persona, base_value=10)
        entry.archetypes.add(archetype)
        self.assertEqual(regard_matches(self.group, self.cinderi_sheet), [])
        LegendSpreadFactory(legend_entry=entry, value_added=40)
        self.assertEqual(len(regard_matches(self.group, self.cinderi_sheet)), 1)
        self.assertEqual(regard_matches(self.group, self.other_sheet), [])

    def test_deed_under_a_non_presented_persona_does_not_match(self) -> None:
        archetype = PhilosophicalArchetypeFactory()
        RegardRuleFactory(creature_template=self.template, rule={}, deed_archetype=archetype)
        alt = PersonaFactory(character_sheet=self.other_sheet)
        entry = LegendEntryFactory(persona=alt, base_value=10)
        entry.archetypes.add(archetype)
        LegendSpreadFactory(legend_entry=entry, value_added=40)
        self.assertEqual(regard_matches(self.group, self.other_sheet), [])
        self.other_sheet.active_persona = alt
        self.other_sheet.save(update_fields=["active_persona"])
        self.assertEqual(len(regard_matches(self.group, self.other_sheet)), 1)

    def test_drive_strength_shift_is_clamped(self) -> None:
        prop = PropertyFactory()
        drive = CreatureDriveFactory(
            creature_template=self.template, property=prop, strength=DriveStrength.MAJOR
        )
        RegardRuleFactory(creature_template=self.template, rule={}, drive=prop, drive_shift=5)
        self.assertEqual(drive_strength_toward(self.group, drive, self.other_sheet), 3)
        RegardRuleFactory(creature_template=self.template, rule={}, drive=prop, drive_shift=-9)
        self.assertEqual(drive_strength_toward(self.group, drive, self.other_sheet), 0)

    def test_band_shift_sums(self) -> None:
        RegardRuleFactory(creature_template=self.template, rule={}, difficulty_shift_bands=2)
        RegardRuleFactory(creature_template=self.template, rule={}, difficulty_shift_bands=-1)
        self.assertEqual(band_shift_toward(self.group, self.other_sheet), 1)
