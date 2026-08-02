"""Every technique surface carries the same effect block (#2898).

Four serializers grew independently and disagreed about what a technique is —
CG had no cost, reach, targeting or hostility at the moment the pick is least
reversible, and the in-scene cast list had no description at all. These tests
pin the shared block onto each of them so they cannot drift apart again.
"""

from __future__ import annotations

from django.test import TestCase

from world.character_creation.serializers import CGTechniqueOptionSerializer
from world.conditions.factories import ConditionTemplateFactory
from world.magic.factories import (
    BinaryEffectTypeFactory,
    TechniqueAppliedConditionFactory,
    TechniqueFactory,
)
from world.magic.models.techniques import ConditionTargetKind
from world.magic.serializers import TechniqueSerializer
from world.scenes.action_serializers import CastableTechniqueSerializer

#: Every key the shared block promises. A surface that ships a subset has drifted.
EXPECTED_KEYS = {
    "relationship",
    "hostile",
    "target_type",
    "reach",
    "reach_hops",
    "arena",
    "anima_cost",
    "applies",
    "removes",
    "damage",
    "grants",
    "summary",
    "is_underspecified",
}


class TechniqueEffectSummaryOnEverySurfaceTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.technique = TechniqueFactory(
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            anima_cost=5,
        )
        TechniqueAppliedConditionFactory(
            technique=cls.technique,
            condition=ConditionTemplateFactory(name="Guarded"),
            target_kind=ConditionTargetKind.ALLY,
        )

    def test_magic_api_carries_the_block_and_the_arena(self):
        """action_category reached no surface at all before #2898."""
        data = TechniqueSerializer(self.technique).data

        self.assertEqual(set(data["effect_summary"]), EXPECTED_KEYS)
        self.assertEqual(data["action_category"], self.technique.action_category)

    def test_cg_option_carries_the_block(self):
        """CG was the thinnest of the four — no cost, reach, targeting or hostility."""
        data = CGTechniqueOptionSerializer(self.technique).data

        self.assertEqual(set(data["effect_summary"]), EXPECTED_KEYS)
        self.assertEqual(data["effect_summary"]["anima_cost"], 5)
        self.assertEqual(data["effect_summary"]["reach"], self.technique.reach)
        self.assertEqual(
            data["effect_summary"]["relationship"],
            ConditionTargetKind.ALLY.value,
        )
        self.assertFalse(data["effect_summary"]["hostile"])

    def test_castable_list_carries_the_block_and_the_description(self):
        """The cast list returned numbers and no prose, so a chosen technique was
        unrecognisable at the moment of casting it."""
        data = CastableTechniqueSerializer(self.technique).data

        self.assertEqual(set(data["effect_summary"]), EXPECTED_KEYS)
        self.assertEqual(data["description"], self.technique.description)
        self.assertNotEqual(data["description"], "")

    def test_castable_hostile_flag_cannot_disagree_with_the_block(self):
        """The pre-existing top-level flag now reads off the same summary."""
        data = CastableTechniqueSerializer(self.technique).data

        self.assertEqual(data["hostile"], data["effect_summary"]["hostile"])

    def test_castable_list_is_fed_technique_rows(self):
        """castable_techniques_for_sheet — the list's only source — yields Techniques.

        The serializer previously carried a CharacterTechnique branch in two
        method fields that could never run; its declared ``name`` field raises on
        a link first. This pins the shape the serializer actually receives.
        """
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import CharacterTechniqueFactory
        from world.magic.models.techniques import Technique
        from world.scenes.cast_services import castable_techniques_for_sheet

        sheet = CharacterSheetFactory()
        CharacterTechniqueFactory(character=sheet, technique=self.technique)

        rows = castable_techniques_for_sheet(sheet.pk)

        self.assertTrue(all(isinstance(row, Technique) for row in rows))
