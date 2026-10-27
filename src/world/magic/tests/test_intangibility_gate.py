"""Intangible personas stay targetable by area casts (#4742; was excluded in #1584 Task 8).

Uses direct ConditionInstance factory construction (not apply_condition) so these tests
run on the SQLite fast tier without hitting the PG-only DISTINCT ON path.
"""

from django.test import TestCase

from actions.constants import ActionTargetType
from world.conditions.factories import (
    ConditionCategoryFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.magic.factories import (
    BinaryEffectTypeFactory,
    TechniqueAppliedConditionFactory,
    TechniqueFactory,
)
from world.magic.models.techniques import ConditionTargetKind
from world.magic.services.targeting import resolve_targets
from world.scenes.factories import InteractionFactory, PersonaFactory, SceneFactory


class IntangibilityGateCastTests(TestCase):
    """An incorporeal bearer is protected by resistance, never by leaving the target set."""

    def _add_to_scene(self, scene, persona):
        InteractionFactory(scene=scene, persona=persona)

    def _make_intangibility_instance(self, character_objectdb):
        """Build an active intangibility ConditionInstance directly via factory (SQLite-safe)."""
        category = ConditionCategoryFactory(grants_intangibility=True)
        template = ConditionTemplateFactory(category=category)
        return ConditionInstanceFactory(condition=template, target=character_objectdb)

    def test_intangible_persona_is_caught_by_an_area_cast(self):
        """An AREA cast includes the intangible persona alongside the tangible one."""
        tech = TechniqueFactory(
            target_type=ActionTargetType.AREA,
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
        )
        TechniqueAppliedConditionFactory(technique=tech, target_kind=ConditionTargetKind.ALLY)

        initiator = PersonaFactory()
        intangible = PersonaFactory()
        tangible = PersonaFactory()

        scene = SceneFactory()
        self._add_to_scene(scene, initiator)
        self._add_to_scene(scene, intangible)
        self._add_to_scene(scene, tangible)

        self._make_intangibility_instance(intangible.character_sheet.character)

        result = resolve_targets(
            technique=tech,
            initiator_persona=initiator,
            scene=scene,
            supplied_personas=[],
        )

        result_ids = {p.pk for p in result}
        self.assertIn(intangible.pk, result_ids, "Intangible persona is still an AREA target")
        self.assertIn(tangible.pk, result_ids, "Tangible persona must still appear in AREA result")
