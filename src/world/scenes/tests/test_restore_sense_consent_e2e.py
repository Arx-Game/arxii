"""Live-path coverage for social-action dispatch — the Fury Restore-to-Sense loop (#1172).

Social actions were not dispatchable on the live player path: ``_scene_actions``
emitted a mangled slug for multi-word templates, ``create_action_request`` never set
``action_template``, and the consent resolution bypassed the action's effect dispatch.
These tests pin the three fixes:

1. ``_scene_actions`` emits the canonical registry key ("restore_sense"), not
   ``template.name.lower()`` ("restore to sense").
2. ``create_action_request`` resolves and persists the ActionTemplate from the
   registry action's ``template_name``.
3. End-to-end (``@tag("postgres")``): accepting a Restore-to-Sense request removes
   the Berserk condition from the target ally via the consent path.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase, tag

from actions.constants import ResolutionPhase
from actions.factories import ActionTemplateFactory
from actions.player_interface import _scene_actions
from actions.types import PendingActionResolution, StepResult
from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckCategoryFactory, CheckTypeFactory
from world.conditions.services import apply_condition, has_condition
from world.magic.factories import (
    BerserkConditionTemplateFactory,
    RestoreToSenseActionTemplateFactory,
)
from world.scenes.action_constants import ConsentDecision
from world.scenes.action_services import create_action_request, respond_to_action_request
from world.scenes.factories import PersonaFactory, SceneFactory


def _make_pending_resolution(*, success: bool = True) -> PendingActionResolution:
    """Minimal PendingActionResolution so the mocked check chain has a main_result."""
    check_result = MagicMock()
    check_result.success_level = 1 if success else -1
    check_result.outcome_name = "Success" if success else "Failure"
    check_result.outcome = None
    main_result = StepResult(step_label="main", check_result=check_result, consequence_id=None)
    return PendingActionResolution(
        template_id=1,
        character_id=1,
        target_difficulty=10,
        resolution_context_data={"character_id": 1, "challenge_instance_id": None},
        current_phase=ResolutionPhase.COMPLETE,
        main_result=main_result,
    )


class SceneActionsSlugTests(TestCase):
    """``_scene_actions`` keys multi-word social templates by their registry key (#1172)."""

    def test_multi_word_template_uses_registry_key_not_name_lower(self) -> None:
        ActionTemplateFactory(name="Restore to Sense", category="social", consequence_pool=None)

        actions = _scene_actions(MagicMock())
        restore = next(
            (
                a
                for a in actions
                if a.action_template and a.action_template.name == "Restore to Sense"
            ),
            None,
        )
        self.assertIsNotNone(restore, "Restore to Sense not surfaced by _scene_actions")
        # name.lower() would yield "restore to sense" (spaces) and miss get_action().
        self.assertEqual(restore.ref.registry_key, "restore_sense")

    def test_single_word_template_still_resolves(self) -> None:
        ActionTemplateFactory(name="Intimidate", category="social", consequence_pool=None)

        actions = _scene_actions(MagicMock())
        intimidate = next(
            (a for a in actions if a.action_template and a.action_template.name == "Intimidate"),
            None,
        )
        self.assertIsNotNone(intimidate)
        self.assertEqual(intimidate.ref.registry_key, "intimidate")


class CreateActionRequestTemplateResolutionTests(TestCase):
    """``create_action_request`` resolves ``action_template`` from the registry action (#1172)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()
        cls.target = PersonaFactory()

    def test_social_action_key_resolves_template(self) -> None:
        template = ActionTemplateFactory(
            name="Restore to Sense", category="social", consequence_pool=None
        )
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="restore_sense",
        )
        self.assertEqual(request.action_template_id, template.pk)

    def test_unseeded_template_leaves_request_template_less(self) -> None:
        # No "Intimidate" ActionTemplate seeded → resolution returns None, unchanged.
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="intimidate",
        )
        self.assertIsNone(request.action_template_id)

    def test_unregistered_action_key_leaves_request_template_less(self) -> None:
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="anima_ritual",
        )
        self.assertIsNone(request.action_template_id)


@tag("postgres")
class RestoreSenseConsentE2ETests(TestCase):
    """End-to-end: accepting a Restore-to-Sense request removes Berserk (#1172 / #567).

    Tagged ``postgres`` because ``remove_condition`` walks active conditions via
    ``DISTINCT ON`` — Postgres-only.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.berserk = BerserkConditionTemplateFactory()
        cls.check_cat = CheckCategoryFactory(name="Social")
        cls.check_type = CheckTypeFactory(name="Willpower", category=cls.check_cat)
        # Seeds the "Restore to Sense" template + ActionEnhancement +
        # RemoveConditionOnCheckConfig(condition=berserk).
        RestoreToSenseActionTemplateFactory(check_type=cls.check_type)

        cls.initiator_character = CharacterFactory()
        cls.initiator_sheet = CharacterSheetFactory(character=cls.initiator_character)
        cls.initiator_persona = cls.initiator_sheet.primary_persona

        cls.target_character = CharacterFactory()
        cls.target_sheet = CharacterSheetFactory(character=cls.target_character)
        cls.target_persona = cls.target_sheet.primary_persona

        cls.scene = SceneFactory(is_active=True)

    def setUp(self) -> None:
        self.accrue_patcher = patch("world.scenes.action_services.accrue")
        self.accrue_patcher.start()
        self.addCleanup(self.accrue_patcher.stop)

    @patch("actions.effects.conditions.perform_check")
    @patch("world.scenes.action_services.start_action_resolution")
    def test_accepting_restore_sense_removes_berserk(
        self, mock_resolve: MagicMock, mock_check: MagicMock
    ) -> None:
        # The talk-down check (consent template) and the remove-condition check both
        # succeed so the effect fires.
        mock_resolve.return_value = _make_pending_resolution(success=True)
        mock_check.return_value = MagicMock(success_level=1)

        apply_condition(self.target_character, self.berserk)
        self.assertTrue(
            has_condition(self.target_character, self.berserk),
            "precondition: target should be Berserk before Restore to Sense",
        )

        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator_persona,
            target_persona=self.target_persona,
            action_key="restore_sense",
        )
        # The fix makes create resolve the template — no manual attach (cf. the old
        # test_targeted_action_e2e which had to set request.action_template by hand).
        self.assertEqual(request.action_template.name, "Restore to Sense")

        respond_to_action_request(action_request=request, decision=ConsentDecision.ACCEPT)

        self.assertFalse(
            has_condition(self.target_character, self.berserk),
            "Berserk should be removed from the target after Restore to Sense resolves",
        )
