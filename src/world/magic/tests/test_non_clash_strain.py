"""Integration test for #547: strain-pushed non-clash cast accrues Soulfray.

This is the headline integration test for the non-clash casting plan. It
exercises the full plumbing path:

  SceneActionRequest (strain_commitment=N) -> respond_to_action_request
  -> _resolve_enhanced_action -> use_technique -> deduct_anima -> Soulfray
  accumulation -> _create_result_interaction with strain_committed audit.

When the caster commits more strain than they have anima, the deduction
deficit drives Soulfray severity above zero (per ``calculate_soulfray_severity``)
and a ConditionInstance(name=SOULFRAY_CONDITION_NAME) is created on the
character. The audit value ``Interaction.strain_committed`` records exactly
the committed amount.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase, tag

from actions.constants import ResolutionPhase
from actions.factories import ActionTemplateFactory
from actions.models import ActionEnhancement
from actions.types import PendingActionResolution, StepResult
from world.conditions.models import ConditionInstance
from world.magic.audere import SOULFRAY_CONDITION_NAME
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    SoulfrayConfigFactory,
    SoulfrayContentFactory,
    TechniqueFactory,
)
from world.scenes.action_constants import ActionRequestStatus, ConsentDecision
from world.scenes.action_services import respond_to_action_request
from world.scenes.factories import PersonaFactory, SceneActionRequestFactory, SceneFactory


def _make_pending_resolution(success: bool = True) -> PendingActionResolution:
    """Build a minimal PendingActionResolution mock for the resolve pipeline."""
    check_result = MagicMock()
    check_result.success_level = 1 if success else -1
    check_result.outcome_name = "Success" if success else "Failure"
    check_result.outcome = None
    main_result = StepResult(
        step_label="main",
        check_result=check_result,
        consequence_id=None,
    )
    return PendingActionResolution(
        template_id=1,
        character_id=1,
        target_difficulty=10,
        resolution_context_data={"character_id": 1, "challenge_instance_id": None},
        current_phase=ResolutionPhase.COMPLETE,
        main_result=main_result,
    )


@tag("postgres")
class StrainPushedNonClashCastTests(TestCase):
    """Strain-commit beyond available anima drives Soulfray accrual.

    Tagged ``postgres`` because the Soulfray accumulation path calls
    ``apply_condition``, which uses ``DISTINCT ON`` to deduplicate stage
    rows by condition_id — a Postgres-only feature unsupported by SQLite.
    The parity tier (CI + ``just test-parity``) exercises this test.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()
        cls.target = PersonaFactory()
        cls.action_template = ActionTemplateFactory()

        cls.sheet = cls.initiator.character_sheet
        cls.character = cls.sheet.character

        # Magic plumbing: technique + character knowledge + enhancement link.
        cls.technique = TechniqueFactory(
            name="Aetheric Lash",
            anima_cost=2,
            intensity=1,
            control=1,
            damage_profile=False,
        )
        CharacterTechniqueFactory(character=cls.sheet, technique=cls.technique)
        ActionEnhancement.objects.create(
            base_action_key="intimidate",
            variant_name="Aetheric Lash Intimidate",
            source_type="technique",
            technique=cls.technique,
        )

        # Soulfray content (template + 5 stages) and config thresholds.
        cls.soulfray_content = SoulfrayContentFactory()
        cls.soulfray_template = cls.soulfray_content.template
        cls.soulfray_config = SoulfrayConfigFactory()

    def setUp(self) -> None:
        # Patch kudos to avoid loading the social_engagement KudosSourceCategory.
        self.award_kudos_patcher = patch("world.scenes.action_services.award_kudos")
        self.mock_award_kudos = self.award_kudos_patcher.start()

        # Fresh anima per test: 5 current vs. strain_commitment=8 → deficit=3.
        self.anima = CharacterAnimaFactory(
            character=self.character,
            current=5,
            maximum=10,
        )

    def tearDown(self) -> None:
        self.award_kudos_patcher.stop()

    @patch("world.scenes.action_services.start_action_resolution")
    def test_strain_pushed_cast_accrues_soulfray_and_records_audit(
        self, mock_resolve: MagicMock
    ) -> None:
        """Strain commit > available anima → Soulfray accrues + interaction records strain."""
        mock_resolve.return_value = _make_pending_resolution(success=True)

        request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="intimidate",
            status=ActionRequestStatus.PENDING,
            technique=self.technique,
            strain_commitment=8,
        )
        request.action_template = self.action_template
        request.save(update_fields=["action_template"])

        respond_to_action_request(action_request=request, decision=ConsentDecision.ACCEPT)

        # 1. Request resolved + result interaction created.
        request.refresh_from_db()
        self.assertEqual(request.status, ActionRequestStatus.RESOLVED)
        self.assertIsNotNone(request.result_interaction)

        # 2. Strain audit recorded on the result Interaction.
        self.assertEqual(request.result_interaction.strain_committed, 8)

        # 3. Anima fully depleted (8 deducted from 5 → clamped to 0).
        self.anima.refresh_from_db()
        self.assertEqual(self.anima.current, 0)

        # 4. Soulfray condition instance exists for the caster with positive severity.
        soulfray_inst = ConditionInstance.objects.filter(
            target=self.character,
            condition__name=SOULFRAY_CONDITION_NAME,
        ).first()
        self.assertIsNotNone(
            soulfray_inst,
            "Expected a Soulfray ConditionInstance to be created on the caster.",
        )
        self.assertGreater(
            soulfray_inst.severity,
            0,
            "Expected positive Soulfray severity from strain-pushed cast deficit.",
        )
