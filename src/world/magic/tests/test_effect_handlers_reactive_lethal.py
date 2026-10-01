"""_try_spend_reactive threads the right lethal value (#4098 fix round 3).

A consented reactive ward/interpose fire debits anima and accrues Soulfray
through the same single ``lethal`` value (world.magic.services.effect_handlers
._try_spend_reactive). Out of combat (or in a non-COMBAT engagement) that value
must be False, so the spend clamps to available anima (no overburn) and
Soulfray can never select a character_loss consequence (#4098 fix round 2). In
a LETHAL CombatEncounter it must be True.
"""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory, ConsequenceFactory
from world.combat.constants import RiskLevel
from world.combat.factories import CombatEncounterFactory
from world.combat.models import CombatEncounter
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.conditions.models import ConditionInstance
from world.magic.audere import SOULFRAY_CONDITION_NAME
from world.magic.factories import CharacterAnimaFactory, SoulfrayConfigFactory
from world.magic.services.anima import deduct_anima
from world.magic.services.effect_handlers import _try_spend_reactive
from world.mechanics.constants import EngagementType
from world.mechanics.factories import CharacterEngagementFactory
from world.traits.factories import CheckOutcomeFactory

# accumulate_soulfray is imported at MODULE level in effect_handlers.py
# (`from world.magic.services.soulfray import accumulate_soulfray`), so the bound
# name in that module's own namespace is what must be patched — a lazy
# per-call import would instead patch the origin module (repo convention, see
# world/combat/tests/test_resolve_combat_technique_fury.py). Patched as a plain
# replacement (not wraps=): accumulate_soulfray's real path would create and
# progress a real Soulfray ConditionInstance, which hits a PG-only DISTINCT ON
# query (world.conditions.services apply_condition, progressive templates) —
# this test stays on the SQLite fast tier, so only the lethal kwarg it receives
# is asserted, not its internal behavior (already covered by
# world.magic.tests.test_nonlethal_cap and world.vitals.tests.test_certain_death).
_ACCUMULATE_SOULFRAY_PATCH = "world.magic.services.effect_handlers.accumulate_soulfray"
# deduct_anima is imported lazily inside _try_spend_reactive
# (`from world.magic.services.anima import deduct_anima`) — patch the origin
# module. wraps= the real function so the clamping arithmetic actually runs
# (pure, SQLite-safe — no condition machinery involved).
_DEDUCT_ANIMA_PATCH = "world.magic.services.anima.deduct_anima"


def _build_consented_ward(*, character) -> ConditionInstance:
    """A self-cast, consented reactive ward costing 10 anima on *character*."""
    template = ConditionTemplateFactory(reactive_anima_cost=10)
    return ConditionInstanceFactory(
        target=character,
        condition=template,
        soulfray_consented=True,
    )


def _seed_death_risk_soulfray_stage() -> None:
    """A death-risk Soulfray stage (character_loss consequence) — unreached by
    this test's mocked accumulate_soulfray, but present so the scenario is
    realistic: if the lethal kwarg regressed back to True, there would be a
    real character_loss consequence downstream capable of killing the payer."""
    SoulfrayConfigFactory(resilience_check_type=CheckTypeFactory())
    tier = CheckOutcomeFactory(name="Soulfray reactive death tier", success_level=-3)
    pool = ConsequencePoolFactory(name="Soulfray reactive death-risk (test)")
    loss = ConsequenceFactory(outcome_tier=tier, label="Lost", character_loss=True)
    ConsequencePoolEntryFactory(pool=pool, consequence=loss)
    soulfray_template = ConditionTemplateFactory(name=SOULFRAY_CONDITION_NAME, has_progression=True)
    ConditionStageFactory(condition=soulfray_template, stage_order=5, consequence_pool=pool)


class OutOfCombatReactiveFireIsNonLethalTests(TestCase):
    def test_out_of_combat_reactive_fire_is_non_lethal(self) -> None:
        sheet = CharacterSheetFactory()
        character = sheet.character
        anima = CharacterAnimaFactory(character=sheet, current=3, maximum=20)
        instance = _build_consented_ward(character=character)
        _seed_death_risk_soulfray_stage()

        with (
            patch(_DEDUCT_ANIMA_PATCH, wraps=deduct_anima) as mock_deduct,
            patch(_ACCUMULATE_SOULFRAY_PATCH) as mock_accumulate,
        ):
            result = _try_spend_reactive(instance)

        self.assertTrue(result)
        anima.refresh_from_db()
        self.assertEqual(anima.current, 0)
        mock_deduct.assert_called_once()
        self.assertFalse(mock_deduct.call_args.kwargs["lethal"])
        mock_accumulate.assert_called_once()
        self.assertFalse(mock_accumulate.call_args.kwargs["lethal"])


class LethalCombatReactiveFireIsLethalTests(TestCase):
    def test_lethal_combat_engagement_reactive_fire_is_lethal(self) -> None:
        sheet = CharacterSheetFactory()
        character = sheet.character
        anima = CharacterAnimaFactory(character=sheet, current=3, maximum=20)
        instance = _build_consented_ward(character=character)
        _seed_death_risk_soulfray_stage()

        encounter = CombatEncounterFactory(risk_level=RiskLevel.LETHAL)
        self.assertTrue(encounter.is_lethal)
        CharacterEngagementFactory(
            character=sheet,
            engagement_type=EngagementType.COMBAT,
            source_content_type=ContentType.objects.get_for_model(CombatEncounter),
            source_id=encounter.pk,
        )

        with (
            patch(_DEDUCT_ANIMA_PATCH, wraps=deduct_anima) as mock_deduct,
            patch(_ACCUMULATE_SOULFRAY_PATCH) as mock_accumulate,
        ):
            result = _try_spend_reactive(instance)

        self.assertTrue(result)
        anima.refresh_from_db()
        mock_deduct.assert_called_once()
        self.assertTrue(mock_deduct.call_args.kwargs["lethal"])
        mock_accumulate.assert_called_once()
        self.assertTrue(mock_accumulate.call_args.kwargs["lethal"])
