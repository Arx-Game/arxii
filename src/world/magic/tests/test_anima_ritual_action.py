"""Tests for the anima_ritual action resolver and menu contributor.

Tests verify:
- The resolver fires apply_anima_ritual_outcome when an anima_ritual action is accepted.
- The menu contributor returns an entry when a character has a CharacterAnimaRitual and
  has not yet spent the once-per-scene cap.
- The menu contributor returns [] when scene=None, cap is spent, or no ritual configured.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from actions.constants import ResolutionPhase
from actions.factories import ActionTemplateFactory
from actions.models import ActionTemplate
from actions.types import PendingActionResolution, StepResult
from world.checks.factories import CheckTypeFactory
from world.checks.types import CheckResult
from world.conditions.factories import ConditionTemplateFactory
from world.magic.audere import SOULFRAY_CONDITION_NAME
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterAnimaRitualFactory,
    SoulfrayConfigFactory,
)
from world.magic.models.anima import AnimaRitualPerformance
from world.scenes.action_availability import get_available_scene_actions
from world.scenes.action_constants import ActionRequestStatus, ConsentDecision
from world.scenes.action_resolvers import _MENU_CONTRIBUTORS, _RESOLVER_REGISTRY
from world.scenes.action_services import respond_to_action_request
from world.scenes.factories import PersonaFactory, SceneActionRequestFactory, SceneFactory
from world.traits.factories import CheckOutcomeFactory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PERFORM_CHECK_PATCH = "world.scenes.action_services.start_action_resolution"
_AWARD_KUDOS_PATCH = "world.scenes.action_services.award_kudos"


def _make_pending_resolution(outcome_row: object) -> PendingActionResolution:
    """Build a PendingActionResolution wrapping a real CheckOutcome row."""
    check_type = CheckTypeFactory()
    check_result = CheckResult(
        check_type=check_type,
        outcome=outcome_row,  # type: ignore[arg-type]
        chart=None,
        roller_rank=None,
        target_rank=None,
        rank_difference=0,
        trait_points=0,
        aspect_bonus=0,
        total_points=0,
    )
    main_result = StepResult(
        step_label="main",
        check_result=check_result,
        consequence_id=None,
    )
    return PendingActionResolution(
        template_id=1,
        character_id=1,
        target_difficulty=15,
        resolution_context_data={"character_id": 1, "challenge_instance_id": None},
        current_phase=ResolutionPhase.COMPLETE,
        main_result=main_result,
    )


class AnimaRitualResolverTests(TestCase):
    """The anima_ritual resolver is registered and applies outcome on accept."""

    def setUp(self) -> None:
        # Ensure the resolver module is imported (apps.ready() fires this in real server;
        # Django test runner does call ready(), so this is a belt-and-suspenders guard).
        from world.magic.services import anima_ritual_action  # noqa: F401

        self.award_kudos_patcher = patch(_AWARD_KUDOS_PATCH)
        self.mock_award_kudos = self.award_kudos_patcher.start()

    def tearDown(self) -> None:
        self.award_kudos_patcher.stop()

    def _setup_ritual_scene(self, success_level: int = 1) -> tuple:
        """Create a full ritual+scene setup and a real CheckOutcome row."""
        persona = PersonaFactory()
        sheet = persona.character_sheet
        target_persona = PersonaFactory()

        ritual = CharacterAnimaRitualFactory(character=sheet)
        anima = CharacterAnimaFactory(
            character=sheet.character,
            current=2,
            maximum=10,
        )
        ConditionTemplateFactory(name=SOULFRAY_CONDITION_NAME)
        SoulfrayConfigFactory(
            ritual_budget_critical_success=10,
            ritual_budget_success=6,
            ritual_budget_partial=3,
            ritual_budget_failure=1,
            ritual_severity_cost_per_point=1,
        )
        scene = SceneFactory(is_active=True)
        outcome = CheckOutcomeFactory(
            name=f"TestOutcome_sl{success_level}_{id(object())}",
            success_level=success_level,
        )
        action_template = ActionTemplateFactory()

        action_request = SceneActionRequestFactory(
            scene=scene,
            initiator_persona=persona,
            target_persona=target_persona,
            action_key="anima_ritual",
            status=ActionRequestStatus.PENDING,
        )
        action_request.action_template = action_template
        action_request.save(update_fields=["action_template"])

        return action_request, ritual, anima, outcome

    def test_resolver_is_registered(self) -> None:
        """The 'anima_ritual' action_key is registered in the resolver registry."""
        self.assertIn("anima_ritual", _RESOLVER_REGISTRY)

    def test_accept_recovers_anima(self) -> None:
        """Accepting an anima_ritual request recovers anima via the resolver."""
        action_request, _ritual, anima, outcome = self._setup_ritual_scene(success_level=1)

        with patch(_PERFORM_CHECK_PATCH, return_value=_make_pending_resolution(outcome)):
            respond_to_action_request(
                action_request=action_request, decision=ConsentDecision.ACCEPT
            )

        anima.refresh_from_db()
        # success budget=6, no soulfray, anima goes from 2 to 8
        self.assertEqual(anima.current, 8)

    def test_accept_creates_performance_row(self) -> None:
        """Accepting creates an AnimaRitualPerformance audit row."""
        action_request, ritual, _anima, outcome = self._setup_ritual_scene(success_level=1)

        with patch(_PERFORM_CHECK_PATCH, return_value=_make_pending_resolution(outcome)):
            respond_to_action_request(
                action_request=action_request, decision=ConsentDecision.ACCEPT
            )

        self.assertTrue(AnimaRitualPerformance.objects.filter(ritual=ritual).exists())

    def test_deny_does_not_recover(self) -> None:
        """Denying an anima_ritual request does not call the resolver."""
        action_request, ritual, anima, _outcome = self._setup_ritual_scene(success_level=1)

        respond_to_action_request(action_request=action_request, decision=ConsentDecision.DENY)

        anima.refresh_from_db()
        self.assertEqual(anima.current, 2)  # unchanged
        self.assertFalse(AnimaRitualPerformance.objects.filter(ritual=ritual).exists())

    def test_crit_success_fills_anima_to_max(self) -> None:
        """Crit outcome fills anima to max regardless of budget."""
        action_request, _ritual, anima, outcome = self._setup_ritual_scene(success_level=2)

        with patch(_PERFORM_CHECK_PATCH, return_value=_make_pending_resolution(outcome)):
            respond_to_action_request(
                action_request=action_request, decision=ConsentDecision.ACCEPT
            )

        anima.refresh_from_db()
        self.assertEqual(anima.current, 10)  # maximum

    def test_no_ritual_configured_resolver_no_ops(self) -> None:
        """When initiator has no CharacterAnimaRitual the resolver exits silently."""
        persona = PersonaFactory()
        target_persona = PersonaFactory()
        # No CharacterAnimaRitual created
        ConditionTemplateFactory(name=SOULFRAY_CONDITION_NAME)
        SoulfrayConfigFactory()
        scene = SceneFactory(is_active=True)
        outcome = CheckOutcomeFactory(name="NoRitualOutcome", success_level=1)
        action_template = ActionTemplateFactory()

        action_request = SceneActionRequestFactory(
            scene=scene,
            initiator_persona=persona,
            target_persona=target_persona,
            action_key="anima_ritual",
            status=ActionRequestStatus.PENDING,
        )
        action_request.action_template = action_template
        action_request.save(update_fields=["action_template"])

        with patch(_PERFORM_CHECK_PATCH, return_value=_make_pending_resolution(outcome)):
            # Should not raise
            result = respond_to_action_request(
                action_request=action_request, decision=ConsentDecision.ACCEPT
            )

        self.assertIsNotNone(result)
        self.assertFalse(AnimaRitualPerformance.objects.exists())


class AnimaRitualMenuContributorTests(TestCase):
    """Menu contributor contributes entries based on CharacterAnimaRitual and scene cap."""

    def setUp(self) -> None:
        # Ensure the contributor module is imported.
        from world.magic.services import anima_ritual_action  # noqa: F401

        # Snapshot contributors before test so tearDown can restore state.
        self._original_contributors = list(_MENU_CONTRIBUTORS)

    def tearDown(self) -> None:
        _MENU_CONTRIBUTORS.clear()
        _MENU_CONTRIBUTORS.extend(self._original_contributors)

    def _setup(self) -> tuple:
        """Create persona + ritual + anima + soulfray config."""
        persona = PersonaFactory()
        sheet = persona.character_sheet
        ritual = CharacterAnimaRitualFactory(character=sheet)
        CharacterAnimaFactory(character=sheet.character, current=5, maximum=10)
        ConditionTemplateFactory(name=SOULFRAY_CONDITION_NAME)
        SoulfrayConfigFactory()
        scene = SceneFactory(is_active=True)
        return sheet, ritual, scene

    def test_menu_contribution_when_ritual_configured_and_cap_unspent(self) -> None:
        """Character with a ritual and no prior performance in scene gets an entry."""
        sheet, ritual, scene = self._setup()

        actions = get_available_scene_actions(character=sheet.character, scene=scene)
        ritual_entries = [a for a in actions if a.action_key == "anima_ritual"]
        self.assertEqual(len(ritual_entries), 1)
        self.assertEqual(ritual_entries[0].display_name, "Anima Ritual")
        self.assertEqual(ritual_entries[0].ritual_id, ritual.id)
        self.assertIsNone(ritual_entries[0].action_template)

    def test_menu_contribution_filtered_when_cap_spent(self) -> None:
        """After once-per-scene cap consumed, anima_ritual entry not in available actions."""
        sheet, ritual, scene = self._setup()
        outcome = CheckOutcomeFactory(name="CapSpentOutcome", success_level=1)

        # Record a performance to consume the cap
        AnimaRitualPerformance.objects.create(
            ritual=ritual,
            scene=scene,
            was_successful=True,
            anima_recovered=3,
            outcome=outcome,
            severity_reduced=0,
        )

        actions = get_available_scene_actions(character=sheet.character, scene=scene)
        ritual_entries = [a for a in actions if a.action_key == "anima_ritual"]
        self.assertEqual(len(ritual_entries), 0)

    def test_menu_contribution_empty_when_no_scene(self) -> None:
        """When scene=None, contributor returns no entries."""
        sheet, _ritual, _scene = self._setup()

        actions = get_available_scene_actions(character=sheet.character, scene=None)
        ritual_entries = [a for a in actions if a.action_key == "anima_ritual"]
        self.assertEqual(len(ritual_entries), 0)

    def test_menu_contribution_empty_when_no_ritual(self) -> None:
        """Character without a CharacterAnimaRitual gets no anima_ritual entry."""
        persona = PersonaFactory()
        ConditionTemplateFactory(name=SOULFRAY_CONDITION_NAME)
        SoulfrayConfigFactory()
        scene = SceneFactory(is_active=True)

        actions = get_available_scene_actions(
            character=persona.character_sheet.character, scene=scene
        )
        ritual_entries = [a for a in actions if a.action_key == "anima_ritual"]
        self.assertEqual(len(ritual_entries), 0)

    def test_social_action_count_unaffected_for_character_without_ritual(self) -> None:
        """Characters without rituals see only social action templates, not ritual entries."""
        # No ritual setup — plain persona
        persona = PersonaFactory()
        ConditionTemplateFactory(name=SOULFRAY_CONDITION_NAME)
        SoulfrayConfigFactory()
        scene = SceneFactory(is_active=True)

        social_count = ActionTemplate.objects.filter(category="social").count()
        actions = get_available_scene_actions(
            character=persona.character_sheet.character, scene=scene
        )
        self.assertEqual(len(actions), social_count)
