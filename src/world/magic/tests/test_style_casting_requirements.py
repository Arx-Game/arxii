"""Style-gated casting: the caster's Path style contributes capability requirements (#2700).

The behaviour this proves is the whole point of moving ``style`` off ``Technique``:
the requirement follows the CASTER, so the same catalog Technique is castable by one
character and blocked for another. A per-technique requirement cannot express that,
which is why ``StyleCapabilityRequirement`` is not a duplicate of
``TechniqueCapabilityRequirement``.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import PathFactory
from world.conditions.factories import (
    CapabilityTypeFactory,
    ConditionCapabilityEffectFactory,
    ConditionTemplateFactory,
)
from world.conditions.services import apply_condition
from world.magic.factories import (
    StyleCapabilityRequirementFactory,
    TechniqueFactory,
    TechniqueStyleFactory,
)
from world.magic.services.capability_requirements import (
    style_capability_requirements,
    technique_performable,
)
from world.progression.factories import CharacterPathHistoryFactory


class StyleGatedCastingTests(TestCase):
    """A silenced Tomes caster cannot incant; a Whispers caster is unaffected."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.speech = CapabilityTypeFactory(name="speech", innate_baseline=1)

        cls.incantation = TechniqueStyleFactory(name="Incantation")
        StyleCapabilityRequirementFactory(style=cls.incantation, capability=cls.speech)
        cls.subtle = TechniqueStyleFactory(name="Subtle")  # no requirements

        cls.path_tomes = PathFactory(name="Path of Tomes", style=cls.incantation)
        cls.path_whispers = PathFactory(name="Path of Whispers", style=cls.subtle)

        # ONE shared catalog technique — the same row both characters know.
        cls.technique = TechniqueFactory(name="Fireball")

        cls.scholar = CharacterSheetFactory().character
        CharacterSheetFactory(character=cls.scholar)
        CharacterPathHistoryFactory(character=cls.scholar.sheet_data, path=cls.path_tomes)

        cls.spy = CharacterSheetFactory().character
        CharacterSheetFactory(character=cls.spy)
        CharacterPathHistoryFactory(character=cls.spy.sheet_data, path=cls.path_whispers)

        # One template + effect row for the whole class: ConditionTemplateFactory is
        # django_get_or_create on name, so building it per call would collide on the
        # ConditionCapabilityEffect (condition, capability) unique constraint.
        cls.gag = ConditionTemplateFactory(name="Silenced")
        ConditionCapabilityEffectFactory(condition=cls.gag, capability=cls.speech, value=-100)

    def _silence(self, character) -> None:
        apply_condition(character, self.gag)

    def test_both_can_cast_when_unimpaired(self) -> None:
        self.assertTrue(technique_performable(self.scholar.sheet_data, self.technique))
        self.assertTrue(technique_performable(self.spy.sheet_data, self.technique))

    def test_silence_blocks_the_incanter_only(self) -> None:
        """The SAME technique: blocked for the Tomes caster, fine for the Whispers one.

        This is the caster-dependence a per-technique requirement cannot express.
        """
        self._silence(self.scholar)
        self._silence(self.spy)

        self.assertFalse(technique_performable(self.scholar.sheet_data, self.technique))
        self.assertTrue(technique_performable(self.spy.sheet_data, self.technique))

    def test_pathless_caster_is_unrestricted(self) -> None:
        """NPCs / pre-awakening characters contribute no style requirements."""
        nobody = CharacterSheetFactory().character
        CharacterSheetFactory(character=nobody)
        self._silence(nobody)
        self.assertEqual(style_capability_requirements(nobody.sheet_data), [])
        self.assertTrue(technique_performable(nobody.sheet_data, self.technique))

    def test_path_without_a_style_is_unrestricted(self) -> None:
        """A path that authors no style imposes nothing (Path.style is nullable)."""
        drifter = CharacterSheetFactory().character
        CharacterSheetFactory(character=drifter)
        CharacterPathHistoryFactory(
            character=drifter.sheet_data, path=PathFactory(name="The Wanderer")
        )
        self._silence(drifter)
        self.assertEqual(style_capability_requirements(drifter.sheet_data), [])
        self.assertTrue(technique_performable(drifter.sheet_data, self.technique))

    def test_style_requirements_resolve_from_the_current_path(self) -> None:
        """Crossing to a new path swaps which style requirements apply."""
        self.assertEqual(
            [r.capability_id for r in style_capability_requirements(self.scholar.sheet_data)],
            [self.speech.pk],
        )
        CharacterPathHistoryFactory(character=self.scholar.sheet_data, path=self.path_whispers)
        self.assertEqual(style_capability_requirements(self.scholar.sheet_data), [])
