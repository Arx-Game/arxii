"""Soulfray can kill only in combat encounters (#4098 fix round 2).

Scene casts and technique-enhanced social actions are non-combat-encounter call
sites of ``use_technique`` and must pass ``lethal=False`` explicitly, so a
``character_loss`` Soulfray consequence can never be selected there (the
filtering itself is proven by ``world.magic.tests.test_nonlethal_cap`` and
``world.vitals.tests.test_certain_death``; this module proves the real
production call sites thread the right value).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.factories import ActionTemplateFactory
from world.checks.types import ResolutionContext
from world.scenes.action_services import _resolve_enhanced_action
from world.scenes.cast_services import _resolve_cast, derive_cast_difficulty
from world.scenes.tests.cast_test_helpers import CastScenarioMixin, make_benign_castable_technique

# use_technique is imported lazily at each call site via
# `from world.magic.services import use_technique` — patch the re-export point
# (repo convention, see world/combat/tests/test_resolve_combat_technique_fury.py).
_USE_TECHNIQUE_PATCH = "world.magic.services.use_technique"


class StandaloneCastIsNeverLethalTests(CastScenarioMixin, TestCase):
    """``_resolve_cast`` (world.scenes.cast_services) backs standalone technique casts."""

    def test_scene_cast_passes_lethal_false_to_use_technique(self) -> None:
        technique = make_benign_castable_technique()
        character = self.caster.character_sheet.character
        mock_result = MagicMock(confirmed=False)

        with patch(_USE_TECHNIQUE_PATCH, return_value=mock_result) as mock_use:
            _resolve_cast(
                technique=technique,
                character=character,
                target=None,
                difficulty=derive_cast_difficulty(technique),
                character_sheet=self.caster.character_sheet,
            )

        mock_use.assert_called_once()
        self.assertFalse(mock_use.call_args.kwargs["lethal"])


class TechniqueEnhancedSocialActionIsNeverLethalTests(CastScenarioMixin, TestCase):
    """``_resolve_enhanced_action`` (world.scenes.action_services) backs a
    technique attached to an ordinary social action (e.g. a technique entrance)."""

    def test_social_action_passes_lethal_false_to_use_technique(self) -> None:
        technique = make_benign_castable_technique()
        character = self.caster.character_sheet.character
        mock_result = MagicMock(confirmed=False)

        with patch(_USE_TECHNIQUE_PATCH, return_value=mock_result) as mock_use:
            _resolve_enhanced_action(
                character=character,
                technique=technique,
                action_template=ActionTemplateFactory(),
                action_key="flirt",
                difficulty=45,
                context=ResolutionContext(character=character),
            )

        mock_use.assert_called_once()
        self.assertFalse(mock_use.call_args.kwargs["lethal"])
