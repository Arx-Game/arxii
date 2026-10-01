"""Certain death from Soulfray, deferred by Audere until the encounter ends (#4098 d.9)."""

from unittest.mock import MagicMock, patch

from django.test import TestCase
from evennia.utils.idmapper import models as idmapper_models

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory, ConsequenceFactory
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.conditions.services import remove_condition
from world.magic.audere import SOULFRAY_CONDITION_NAME
from world.magic.factories import (
    AudereThresholdFactory,
    SoulfrayConfigFactory,
    wire_audere_power_multipliers,
)
from world.magic.services.soulfray import _fire_stage_consequence_pool
from world.traits.factories import CheckOutcomeFactory
from world.vitals.constants import CharacterLifeState
from world.vitals.factories import CharacterVitalsFactory
from world.vitals.models import CharacterVitals
from world.vitals.services import defer_or_apply_certain_death


class CertainDeathTests(TestCase):
    def setUp(self) -> None:
        idmapper_models.flush_cache()
        self.audere, self.majora = wire_audere_power_multipliers()
        AudereThresholdFactory(deferred_death_text="PLACEHOLDER line")
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.character.msg = MagicMock()
        CharacterVitalsFactory(character_sheet=self.sheet)

    def _state(self) -> CharacterVitals:
        return CharacterVitals.objects.get(character_sheet=self.sheet)

    def test_dies_now_without_a_deferring_condition(self) -> None:
        self.assertFalse(defer_or_apply_certain_death(self.sheet))
        self.assertEqual(self._state().life_state, CharacterLifeState.DEAD)

    def test_deferred_in_audere_and_told(self) -> None:
        ConditionInstanceFactory(target=self.character, condition=self.audere)
        self.assertTrue(defer_or_apply_certain_death(self.sheet))
        state = self._state()
        self.assertEqual(state.life_state, CharacterLifeState.ALIVE)
        self.assertTrue(state.death_certain_pending)
        self.character.msg.assert_called_with("PLACEHOLDER line")

    def test_death_applies_when_audere_ends(self) -> None:
        ConditionInstanceFactory(target=self.character, condition=self.audere)
        defer_or_apply_certain_death(self.sheet)
        remove_condition(self.character, self.audere)
        state = self._state()
        self.assertEqual(state.life_state, CharacterLifeState.DEAD)
        self.assertFalse(state.death_certain_pending)

    def test_death_waits_for_last_deferring_condition(self) -> None:
        ConditionInstanceFactory(target=self.character, condition=self.audere)
        ConditionInstanceFactory(target=self.character, condition=self.majora)
        defer_or_apply_certain_death(self.sheet)
        remove_condition(self.character, self.audere)
        self.assertEqual(self._state().life_state, CharacterLifeState.ALIVE)
        remove_condition(self.character, self.majora)
        self.assertEqual(self._state().life_state, CharacterLifeState.DEAD)


class SoulfrayCharacterLossTests(TestCase):
    """A selected character_loss Soulfray consequence routes through the death seam."""

    def setUp(self) -> None:
        idmapper_models.flush_cache()
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        CharacterVitalsFactory(character_sheet=self.sheet)
        tier = CheckOutcomeFactory(name="Soulfray loss tier", success_level=-3)
        pool = ConsequencePoolFactory(name="Soulfray lethal (test)")
        self.loss = ConsequenceFactory(outcome_tier=tier, label="Lost", character_loss=True)
        ConsequencePoolEntryFactory(pool=pool, consequence=self.loss)
        template = ConditionTemplateFactory(name=SOULFRAY_CONDITION_NAME, has_progression=True)
        self.stage = ConditionStageFactory(condition=template, stage_order=5, consequence_pool=pool)
        self.config = SoulfrayConfigFactory(resilience_check_type=CheckTypeFactory())

    def _fire(self, *, lethal: bool):
        pending = MagicMock(selected_consequence=self.loss)
        with (
            patch("world.checks.services.perform_check_with_modifiers"),
            patch(
                "world.checks.consequence_resolution.select_consequence_from_result",
                return_value=pending,
            ),
            patch("world.checks.consequence_resolution.apply_resolution", return_value=[]),
            patch("world.vitals.services.defer_or_apply_certain_death") as seam,
        ):
            _fire_stage_consequence_pool(
                character=self.character,
                current_stage=self.stage,
                soulfray_config=self.config,
                technique_check_result=None,
                lethal=lethal,
            )
        return seam

    def test_character_loss_calls_death_seam(self) -> None:
        self._fire(lethal=True).assert_called_once_with(self.sheet)

    def test_non_lethal_never_calls_death_seam(self) -> None:
        self._fire(lethal=False).assert_not_called()
