"""End-to-end recovery flow integration test for Scope 6 (§9.2).

Exercises every Scope 6 service through a single scenario:
    accumulation → aftermath application → stabilization → ritual recovery
    → anima regen gating → decay-alone-cannot-recover-stage-2 boundary.

Scene participation is patched at the call site that gates the treatment
(`world.conditions.services._scene_participant`) so this test does not
re-exercise roster/account plumbing; that is covered by unit tests in
the service. The anima ritual is never done alone (#5280): the target performs it
with an NPC partner in a scene a GM runs, which the partner is accepted in at once.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from evennia_extensions.factories import AccountFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.conditions.factories import (
    ArcaneTremorTemplateFactory,
    AuraBleedTemplateFactory,
    ConditionInstanceFactory,
    SoulAcheTemplateFactory,
    SoulfrayStabilizeAftermathTreatmentFactory,
)
from world.conditions.models import ConditionInstance
from world.conditions.services import (
    advance_condition_severity,
    decay_all_conditions_tick,
    decay_condition_severity,
    perform_treatment,
)
from world.magic.constants import RitualExecutionKind
from world.magic.factories import (
    AnimaConfigFactory,
    CharacterAnimaFactory,
    RitualCheckConfigFactory,
    RitualFactory,
    SoulfrayConfigFactory,
    SoulfrayContentFactory,
    wire_soulfray_aftermath,
)
from world.magic.models.anima import AnimaRitualPerformance
from world.magic.models.soulfray import AnimaRitualBudgetAward
from world.magic.services.anima import anima_regen_tick
from world.magic.services.anima_ritual_action import start_partner_ritual
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.scenes.interaction_services import invalidate_active_scene_cache
from world.traits.factories import CheckOutcomeFactory

_CONDITIONS_SCENE_PARTICIPANT_PATH = "world.conditions.services._scene_participant"
# perform_check is lazy-imported inside both services; patch the source module.
_PERFORM_CHECK_PATH = "world.checks.services.perform_check"


def _make_check_result(success_level: int) -> MagicMock:
    outcome = CheckOutcomeFactory(
        name=f"IntegrationOutcome_sl_{success_level}_{id(object())}",
        success_level=success_level,
    )
    result = MagicMock()
    result.outcome = outcome
    result.success_level = success_level
    return result


@override_settings(SEED_SAMPLE_CONTENT=True)  # SoulfrayContentFactory gates on #2698
@patch(_CONDITIONS_SCENE_PARTICIPANT_PATH, return_value=True)
class SoulfrayRecoveryFlowIntegrationTests(TestCase):
    """Single-scenario end-to-end test covering the Scope 6 recovery surfaces."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.content = SoulfrayContentFactory()
        cls.soulfray = cls.content.template
        cls.stages = cls.content.stages  # tuple, stage_order 1..5

        # Aftermath templates (required before wire_soulfray_aftermath).
        SoulAcheTemplateFactory()
        ArcaneTremorTemplateFactory()
        AuraBleedTemplateFactory()
        wire_soulfray_aftermath(cls.content)

        cls.soulfray_config = SoulfrayConfigFactory()
        cls.anima_config = AnimaConfigFactory()

        # Aftermath stabilization treatment — disable bond + resonance cost so
        # this test does not re-exercise bond/resonance plumbing (both have
        # their own unit coverage). Reduction values remain the spec defaults.
        cls.stabilize_aftermath = SoulfrayStabilizeAftermathTreatmentFactory(
            requires_bond=False,
            resonance_cost=0,
        )

    # - PLR0915: end-to-end flow; breaking into parts would obscure the scenario
    # - ARG002: mock_cond_scene is injected by the class-level @patch decorator and not
    #   asserted on inside this test
    def test_full_recovery_flow(  # noqa: PLR0915
        self,
        mock_cond_scene: MagicMock,  # noqa: ARG002
    ) -> None:
        # --- 1) Target character accumulates Soulfray to stage 3 (Ripping) ---
        target_sheet = CharacterSheetFactory()
        # Create SCENE_ACTION Ritual for the character via author_account
        _account = AccountFactory()
        target_sheet.character.db_account = _account
        target_sheet.character.save(update_fields=["db_account"])
        _ritual = RitualFactory(
            execution_kind=RitualExecutionKind.SCENE_ACTION,
            service_function_path="",
            flow=None,
            author_account=_account,
        )
        RitualCheckConfigFactory(ritual=_ritual)
        target_anima = CharacterAnimaFactory(
            character=target_sheet,
            current=0,
            maximum=20,
        )
        # The ritual's partner is an NPC in the same room, accepted at once because the scene
        # has a GM; the performer stands in that room and so does the partner.
        room = RoomProfileFactory()
        scene = SceneFactory(location=room, is_active=True)
        SceneParticipationFactory(scene=scene, account=AccountFactory(), is_gm=True)
        partner_sheet = CharacterSheetFactory()
        for sheet in (target_sheet, partner_sheet):
            sheet.character.location = room.objectdb
        invalidate_active_scene_cache(room.objectdb)

        soulfray_inst = ConditionInstanceFactory(
            target=target_sheet.character,
            condition=self.soulfray,
            severity=0,
            current_stage=None,
        )
        # Advance to the Ripping threshold (16). advance_condition_severity
        # walks stages and triggers the stage-entry aftermath hook.
        ripping_threshold = self.stages[2].severity_threshold
        advance_condition_severity(soulfray_inst, amount=ripping_threshold)
        soulfray_inst.refresh_from_db()
        self.assertEqual(soulfray_inst.current_stage_id, self.stages[2].pk)

        # Aftermath soul_ache should have been applied by the stage-entry hook.
        aftermath_qs = ConditionInstance.objects.filter(
            target=target_sheet.character,
            condition__name="soul_ache",
            resolved_at__isnull=True,
        )
        self.assertEqual(aftermath_qs.count(), 1)
        aftermath_inst = aftermath_qs.get()

        # --- 2) Helper performs stabilization on the aftermath ---
        helper_sheet = CharacterSheetFactory()
        with patch(_PERFORM_CHECK_PATH) as mock_check:
            mock_check.return_value = _make_check_result(success_level=1)
            treatment_outcome = perform_treatment(
                helper_sheet=helper_sheet,
                target_sheet=target_sheet,
                scene=scene,
                treatment=self.stabilize_aftermath,
                target_effect=aftermath_inst,
            )
        self.assertGreater(treatment_outcome.severity_reduced, 0)

        # --- 3) Target performs anima ritual (crit) → severity drops AND
        # anima refills to max. Budget=10 (crit), Soulfray severity=16, so
        # 10 budget goes to severity-pay-down, but crit also overrides anima
        # to maximum regardless of leftover budget.
        crit = CheckOutcomeFactory(name=f"IntegrationCrit_{id(object())}", success_level=2)
        AnimaRitualBudgetAward.objects.create(outcome_tier=crit, budget=10)
        with force_check_outcome(crit):
            start_partner_ritual(
                scene=scene,
                initiator_persona=target_sheet.primary_persona,
                target_persona=partner_sheet.primary_persona,
            )
        performance = AnimaRitualPerformance.objects.get(ritual=_ritual, scene=scene)
        soulfray_inst.refresh_from_db()
        target_anima.refresh_from_db()
        self.assertLess(soulfray_inst.severity, ripping_threshold)
        self.assertGreater(performance.severity_reduced, 0)
        self.assertEqual(target_anima.current, target_anima.maximum)

        # --- 4) Anima regen tick: blocked while Soulfray at stage >= 2 ---
        # Force anima below max so the tick examines the row.
        target_anima.current = 0
        target_anima.save(update_fields=["current"])

        tearing_threshold = self.stages[1].severity_threshold  # 6
        iterations = 0
        while soulfray_inst.severity >= tearing_threshold:
            iterations += 1
            self.assertLess(iterations, 30, "safety: decay loop should terminate")
            summary = anima_regen_tick()
            self.assertEqual(summary.regenerated, 0)
            self.assertGreaterEqual(summary.condition_blocked, 1)
            target_anima.refresh_from_db()
            self.assertEqual(target_anima.current, 0)
            decay_condition_severity(soulfray_inst, amount=1)
            soulfray_inst.refresh_from_db()

        # --- 5) At stage 1 (Fraying), next tick regens anima ---
        summary = anima_regen_tick()
        self.assertGreaterEqual(summary.regenerated, 1)
        target_anima.refresh_from_db()
        self.assertGreater(target_anima.current, 0)

        # --- 6) Boundary: passive decay alone cannot recover from stage 2 ---
        # passive_decay_max_severity is set to Tearing.threshold - 1 = 5, so
        # once severity is in Tearing (>= 6), decay_all_conditions_tick is a
        # no-op.
        isolated_sheet = CharacterSheetFactory()
        mid_stage_inst = ConditionInstanceFactory(
            target=isolated_sheet.character,
            condition=self.soulfray,
            severity=0,
            current_stage=None,
        )
        advance_condition_severity(mid_stage_inst, amount=tearing_threshold + 2)
        mid_stage_inst.refresh_from_db()
        self.assertEqual(mid_stage_inst.current_stage_id, self.stages[1].pk)
        initial_severity = mid_stage_inst.severity

        for _ in range(10):
            decay_all_conditions_tick()

        mid_stage_inst.refresh_from_db()
        self.assertEqual(mid_stage_inst.severity, initial_severity)
        self.assertEqual(mid_stage_inst.current_stage_id, self.stages[1].pk)
