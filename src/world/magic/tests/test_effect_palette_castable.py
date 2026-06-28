"""Verify all 9 seeded effect Techniques have a non-null action_template (#1584, Task 14d).

SQLite-safe: no ``apply_condition``, no ``@tag("postgres")``.  Checks only the
``action_template`` FK on each Technique row — no combat or condition machinery.
"""

from django.test import TestCase

from world.magic.effect_palette_content import (
    BLINK_TECHNIQUE_NAME,
    FORCE_FIELD_TECHNIQUE_NAME,
    INCORPOREAL_TECHNIQUE_NAME,
    OBSTACLE_TECHNIQUE_NAME,
    REFLECT_TECHNIQUE_NAME,
    SINK_TECHNIQUE_NAME,
    SUMMON_TECHNIQUE_NAME,
    TELEKINESIS_TECHNIQUE_NAME,
    TELEPORT_TECHNIQUE_NAME,
    ensure_effect_palette_content,
)
from world.magic.models.techniques import Technique
from world.magic.seeds_cast import get_standalone_cast_template

_ALL_NINE_NAMES = [
    SUMMON_TECHNIQUE_NAME,
    FORCE_FIELD_TECHNIQUE_NAME,
    REFLECT_TECHNIQUE_NAME,
    BLINK_TECHNIQUE_NAME,
    TELEPORT_TECHNIQUE_NAME,
    OBSTACLE_TECHNIQUE_NAME,
    INCORPOREAL_TECHNIQUE_NAME,
    SINK_TECHNIQUE_NAME,
    TELEKINESIS_TECHNIQUE_NAME,
]


class EffectPaletteCastableTests(TestCase):
    """All 9 effect Techniques must carry a non-null action_template after seeding."""

    @classmethod
    def setUpTestData(cls) -> None:
        ensure_effect_palette_content()
        cls.expected_template = get_standalone_cast_template()

    def test_all_nine_techniques_have_action_template(self) -> None:
        """Every seeded effect Technique has action_template set (not None)."""
        for name in _ALL_NINE_NAMES:
            with self.subTest(technique=name):
                tech = Technique.objects.get(name=name)
                self.assertIsNotNone(
                    tech.action_template,
                    f"Technique '{name}' has action_template=None — not castable.",
                )

    def test_all_nine_techniques_use_standalone_cast_template(self) -> None:
        """Every seeded effect Technique points at the shared Technique Cast template."""
        for name in _ALL_NINE_NAMES:
            with self.subTest(technique=name):
                tech = Technique.objects.get(name=name)
                self.assertEqual(
                    tech.action_template_id,
                    self.expected_template.pk,
                    f"Technique '{name}' action_template_id mismatch.",
                )
